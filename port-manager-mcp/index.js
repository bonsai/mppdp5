#!/usr/bin/env node
// port-manager-mcp (local fork)
// ---------------------------------------------------------------------------
// Upstream: port-manager-mcp v1.0.2 (tools: check_port / find_free_port /
// kill_process). This local fork vendors that server verbatim and adds a
// fourth tool, `network_system_view`, which returns a single structured
// snapshot of the host's network + system state (interfaces, listening ports
// with owning processes, connection states, routes, DNS).
//
// Register with opencode as:
//   { "type": "local", "command": ["node", "<abs>/index.js"] }
// ---------------------------------------------------------------------------
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { createServer } from 'node:net';
import { exec, execFile } from 'node:child_process';
import {
    platform as osPlatform,
    hostname as osHostname,
    release as osRelease,
    arch as osArch,
    uptime as osUptime,
    totalmem as osTotalmem,
    freemem as osFreemem,
    cpus as osCpus,
    loadavg as osLoadavg,
    networkInterfaces as osNetworkInterfaces,
} from 'node:os';
import { promisify } from 'node:util';

const execAsync = promisify(exec);
const execFileAsync = promisify(execFile);

// ============================================================
// Constants
// ============================================================
const DEFAULT_PORT_RANGE = { start: 3000, end: 9000 };
const DEFAULT_FIND_COUNT = 5;
const WSL_DISTRO = process.env.PORTMAN_WSL_DISTRO || 'Ubuntu';

// ============================================================
// Port Utilities (verbatim from upstream)
// ============================================================
/** Check if a port is available (not in use) */
function isPortFree(port, host = '127.0.0.1') {
    return new Promise((resolve) => {
        const server = createServer();
        server.listen(port, host, () => {
            server.close(() => resolve(true));
        });
        server.on('error', () => resolve(false));
    });
}
/** Find process info using a port number (cross-platform) */
async function findProcessByPort(port) {
    const os = osPlatform();
    try {
        if (os === 'win32') {
            const { stdout } = await execAsync(`netstat -ano | findstr :${port} | findstr LISTENING`);
            const lines = stdout.trim().split('\n').filter(Boolean);
            if (lines.length === 0)
                return null;
            const parts = lines[0].trim().split(/\s+/);
            const pid = parseInt(parts[parts.length - 1], 10);
            if (isNaN(pid))
                return null;
            try {
                const { stdout: taskOut } = await execAsync(`tasklist /FI "PID eq ${pid}" /NH`);
                const taskLine = taskOut.trim().split('\n')[0];
                const taskParts = taskLine.trim().split(/\s+/);
                const name = taskParts[0] || 'unknown';
                return { pid, name, command: taskLine.trim() };
            }
            catch {
                return { pid, name: 'unknown', command: `PID ${pid}` };
            }
        }
        else {
            const { stdout } = await execAsync(`lsof -i :${port} -P -n | grep LISTEN`);
            const lines = stdout.trim().split('\n').filter(Boolean);
            if (lines.length === 0)
                return null;
            const parts = lines[0].trim().split(/\s+/);
            const name = parts[0] || 'unknown';
            const pid = parseInt(parts[1], 10);
            const command = lines[0].trim();
            return { pid: isNaN(pid) ? 0 : pid, name, command };
        }
    }
    catch {
        return null;
    }
}
/** Kill a process by PID (cross-platform) */
async function killProcessByPid(pid, force = true) {
    const os = osPlatform();
    if (os === 'win32') {
        const flag = force ? '/F' : '';
        await execAsync(`taskkill /PID ${pid} ${flag}`);
    }
    else {
        const signal = force ? '-9' : '-15';
        await execAsync(`kill ${signal} ${pid}`);
    }
}

// ============================================================
// Network System View helpers
// ============================================================

/** Run a shell command, once on the Windows/Linux host or once inside WSL. */
async function sh(cmd, target = 'host') {
    const opts = { maxBuffer: 16 * 1024 * 1024, windowsHide: true };
    if (target === 'wsl') {
        return execFileAsync('wsl.exe', ['-d', WSL_DISTRO, '--', 'bash', '-lc', cmd], opts);
    }
    return execAsync(cmd, opts);
}

function isWindowsHost(target) {
    return target === 'host' && osPlatform() === 'win32';
}

/** Outgoing/incoming interface addresses. */
async function collectInterfaces(target) {
    if (!isWindowsHost(target)) {
        // linux (host or WSL): `ip -o addr`
        const out = [];
        for (const fam of ['-4', '-6']) {
            try {
                const { stdout } = await sh(`ip -o ${fam} addr show`, target);
                for (const line of stdout.split('\n')) {
                    // 2: eth0    inet 172.24.1.2/20 brd ... scope global eth0
                    const m = line.match(/^\s*\d+:\s+(\S+)\s+(\S+)\s+(\S+)\s+/);
                    if (!m) continue;
                    out.push({
                        name: m[1].replace(/@.*$/, ''),
                        family: m[2],
                        address: m[3],
                    });
                }
            }
            catch { /* iproute2 missing — fall back below */ }
        }
        if (out.length) return out;
        // fallback: ifconfig-style
        return [];
    }
    const ifaces = osNetworkInterfaces();
    const out = [];
    for (const [name, addrs] of Object.entries(ifaces)) {
        for (const a of addrs || []) {
            out.push({
                name,
                family: a.family,
                address: a.address,
                netmask: a.netmask,
                mac: a.mac,
                internal: a.internal,
            });
        }
    }
    return out;
}

/** Listening TCP sockets with owning process. */
async function collectListening(target) {
    if (isWindowsHost(target)) {
        const { stdout } = await sh('netstat -ano', target);
        const entries = [];
        const seen = new Set();
        for (const line of stdout.split(/\r?\n/)) {
            const m = line.trim().match(/^TCP\s+(\S+)\s+(\S+)\s+LISTENING\s+(\d+)/i);
            if (!m) continue;
            const local = m[1];
            const pid = parseInt(m[3], 10);
            const port = parseInt(local.slice(local.lastIndexOf(':') + 1), 10);
            const key = `${local}:${pid}`;
            if (seen.has(key)) continue;
            seen.add(key);
            entries.push({ address: local, port, pid, process: 'unknown' });
        }
        // pid -> image name
        const names = {};
        try {
            const { stdout: tl } = await sh('tasklist /FO CSV /NH', target);
            for (const l of tl.split(/\r?\n/)) {
                const cols = l.split('","').map((s) => s.replace(/^"|"$/g, ''));
                if (cols.length >= 2) {
                    const p = parseInt(cols[1], 10);
                    if (!isNaN(p)) names[p] = cols[0];
                }
            }
        }
        catch { /* ignore */ }
        for (const e of entries) e.process = names[e.pid] || 'unknown';
        return entries;
    }
    // linux
    try {
        const { stdout } = await sh('ss -tlnp', target);
        const entries = [];
        for (const line of stdout.split('\n')) {
            const t = line.trim();
            if (!t || /^State\b/.test(t) || /^Netid\b/.test(t)) continue;
            const parts = t.split(/\s+/);
            if (parts.length < 4) continue;
            const local = parts[3];
            const port = parseInt(local.slice(local.lastIndexOf(':') + 1), 10);
            let process = 'unknown';
            let pid = null;
            const pm = t.match(/users:\(\("([^"]+)",pid=(\d+)/);
            if (pm) {
                process = pm[1];
                pid = parseInt(pm[2], 10);
            }
            entries.push({ address: local, port, pid, process });
        }
        return entries;
    }
    catch {
        try {
            const { stdout } = await sh('lsof -nP -iTCP -sTCP:LISTEN', target);
            const entries = [];
            for (const line of stdout.split('\n').slice(1)) {
                const parts = line.trim().split(/\s+/);
                if (parts.length < 9) continue;
                const name = parts[0];
                const pid = parseInt(parts[1], 10);
                const addr = parts[8];
                const port = parseInt(addr.slice(addr.lastIndexOf(':') + 1), 10);
                entries.push({ address: addr, port, pid: isNaN(pid) ? null : pid, process: name });
            }
            return entries;
        }
        catch {
            return [];
        }
    }
}

/** TCP connection state counts. */
async function collectConnectionStates(target) {
    const counts = {};
    try {
        if (isWindowsHost(target)) {
            const { stdout } = await sh('netstat -ano', target);
            for (const line of stdout.split(/\r?\n/)) {
                const parts = line.trim().split(/\s+/);
                if (parts[0] !== 'TCP' || parts.length < 5) continue;
                const state = parts[3];
                counts[state] = (counts[state] || 0) + 1;
            }
        }
        else {
            const { stdout } = await sh('ss -tan', target);
            for (const line of stdout.split('\n').slice(1)) {
                const t = line.trim();
                if (!t) continue;
                const state = t.split(/\s+/)[0];
                counts[state] = (counts[state] || 0) + 1;
            }
        }
    }
    catch { /* ignore */ }
    return counts;
}

/** Default gateway / routes. */
async function collectRoutes(target) {
    const routes = { default_gateway: null, default_interface: null, raw_lines: [] };
    try {
        if (isWindowsHost(target)) {
            const { stdout } = await sh('netstat -rn', target);
            for (const line of stdout.split(/\r?\n/)) {
                const parts = line.trim().split(/\s+/);
                if (parts.length >= 5 && parts[0] === '0.0.0.0' && parts[1] === '0.0.0.0') {
                    routes.default_gateway = parts[2];
                    routes.default_interface = parts[3];
                    routes.raw_lines.push(line.trim());
                }
            }
        }
        else {
            const { stdout } = await sh('ip route', target);
            for (const line of stdout.split('\n')) {
                if (line.startsWith('default')) {
                    const gm = line.match(/via\s+(\S+)/);
                    const dm = line.match(/dev\s+(\S+)/);
                    routes.default_gateway = gm ? gm[1] : null;
                    routes.default_interface = dm ? dm[1] : null;
                    routes.raw_lines.push(line.trim());
                }
            }
        }
    }
    catch { /* ignore */ }
    return routes;
}

/** Configured DNS resolvers. */
async function collectDns(target) {
    const servers = [];
    try {
        if (isWindowsHost(target)) {
            // Preferred: structured, and immune to localized ipconfig labels.
            try {
                const { stdout } = await execFileAsync('powershell.exe', [
                    '-NoProfile', '-NonInteractive', '-Command',
                    'Get-DnsClientServerAddress -AddressFamily IPv4 | Select-Object -ExpandProperty ServerAddresses',
                ], { maxBuffer: 4 * 1024 * 1024, windowsHide: true });
                for (const l of stdout.split(/\r?\n/)) {
                    const t = l.trim();
                    if (/^(\d{1,3}\.){3}\d{1,3}$/.test(t)) servers.push(t);
                }
            }
            catch { /* fall back to ipconfig below */ }
            if (!servers.length) {
                const { stdout } = await sh('ipconfig /all', target);
                const lines = stdout.split(/\r?\n/);
                for (let i = 0; i < lines.length; i++) {
                    // label may be localized ("DNS Servers" / "DNS サーバー") - key on "DNS"
                    const m = lines[i].match(/DNS[^:]*:\s*([0-9a-f:.]+)?/i);
                    if (!m) continue;
                    if (m[1]) servers.push(m[1]);
                    for (let j = i + 1; j < lines.length; j++) {
                        const cont = lines[j].match(/^\s+([0-9a-f:.]+)\s*$/i);
                        if (!cont) break;
                        servers.push(cont[1]);
                    }
                }
            }
        }
        else {
            const { stdout } = await sh('cat /etc/resolv.conf', target);
            for (const line of stdout.split('\n')) {
                const m = line.match(/^\s*nameserver\s+(\S+)/);
                if (m) servers.push(m[1]);
            }
        }
    }
    catch { /* ignore */ }
    return [...new Set(servers)];
}

/** System identity block. */
async function collectSystem(target) {
    if (isWindowsHost(target)) {
        const c = osCpus();
        return {
            hostname: osHostname(),
            platform: osPlatform(),
            release: osRelease(),
            arch: osArch(),
            uptime_seconds: Math.round(osUptime()),
            cpu_model: c[0] ? c[0].model : 'unknown',
            cpu_count: c.length,
            load_avg: osLoadavg(),
            memory_total_bytes: osTotalmem(),
            memory_free_bytes: osFreemem(),
        };
    }
    const info = {
        hostname: null,
        platform: 'linux',
        release: null,
        arch: null,
        uptime_seconds: null,
        cpu_model: null,
        cpu_count: null,
        load_avg: null,
        memory_total_bytes: null,
        memory_free_bytes: null,
    };
    try { info.hostname = (await sh('hostname', target)).stdout.trim(); } catch { /* ignore */ }
    try { info.release = (await sh('uname -r', target)).stdout.trim(); } catch { /* ignore */ }
    try { info.arch = (await sh('uname -m', target)).stdout.trim(); } catch { /* ignore */ }
    try { info.uptime_seconds = parseFloat((await sh('cat /proc/uptime', target)).stdout.trim().split(/\s+/)[0]); } catch { /* ignore */ }
    try {
        const { stdout } = await sh("grep -m1 'model name' /proc/cpuinfo", target);
        const m = stdout.match(/:\s*(.+)$/);
        if (m) info.cpu_model = m[1].trim();
    } catch { /* ignore */ }
    try { info.cpu_count = parseInt((await sh('nproc', target)).stdout.trim(), 10); } catch { /* ignore */ }
    try { info.load_avg = (await sh('cat /proc/loadavg', target)).stdout.trim().split(/\s+/).slice(0, 3).map(Number); } catch { /* ignore */ }
    try {
        const { stdout } = await sh("grep -E '^(MemTotal|MemFree):' /proc/meminfo", target);
        for (const line of stdout.split('\n')) {
            const m = line.match(/^(MemTotal|MemFree):\s+(\d+)\s+kB/);
            if (!m) continue;
            const bytes = parseInt(m[2], 10) * 1024;
            if (m[1] === 'MemTotal') info.memory_total_bytes = bytes;
            else info.memory_free_bytes = bytes;
        }
    } catch { /* ignore */ }
    return info;
}

// ============================================================
// MCP Server
// ============================================================
const server = new McpServer({
    name: 'port-manager',
    version: '1.0.0',
});

// ===== Tool 1: check_port =====
server.registerTool('check_port', {
    title: 'Check Port Status',
    description: 'Check if a port is available or in use. Returns process info if occupied.',
    inputSchema: z.object({
        port: z.number().int().min(1).max(65535).describe('Port number to check'),
        host: z.string().default('127.0.0.1').describe('Host to check (default: 127.0.0.1)'),
    }),
}, async ({ port, host }) => {
    try {
        const isFree = await isPortFree(port, host);
        if (isFree) {
            return {
                content: [{
                        type: 'text',
                        text: JSON.stringify({ port, host, status: 'free' }, null, 2),
                    }],
            };
        }
        const processInfo = await findProcessByPort(port);
        return {
            content: [{
                    type: 'text',
                    text: JSON.stringify({
                        port,
                        host,
                        status: 'in_use',
                        process: processInfo,
                    }, null, 2),
                }],
        };
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return {
            content: [{ type: 'text', text: JSON.stringify({ error: true, message }, null, 2) }],
            isError: true,
        };
    }
});

// ===== Tool 2: find_free_port =====
server.registerTool('find_free_port', {
    title: 'Find Free Ports',
    description: 'Find available ports in a given range.',
    inputSchema: z.object({
        start: z.number().int().min(1).max(65535).default(DEFAULT_PORT_RANGE.start).describe('Start of port range'),
        end: z.number().int().min(1).max(65535).default(DEFAULT_PORT_RANGE.end).describe('End of port range'),
        count: z.number().int().min(1).max(100).default(DEFAULT_FIND_COUNT).describe('Number of free ports to find'),
    }),
}, async ({ start, end, count }) => {
    try {
        if (start > end) {
            return {
                content: [{ type: 'text', text: JSON.stringify({ error: true, message: 'start must be <= end' }, null, 2) }],
                isError: true,
            };
        }
        const freePorts = [];
        for (let port = start; port <= end && freePorts.length < count; port++) {
            if (await isPortFree(port)) {
                freePorts.push(port);
            }
        }
        return {
            content: [{
                    type: 'text',
                    text: JSON.stringify({
                        requested: count,
                        found: freePorts.length,
                        ports: freePorts,
                        range: { start, end },
                    }, null, 2),
                }],
        };
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return {
            content: [{ type: 'text', text: JSON.stringify({ error: true, message }, null, 2) }],
            isError: true,
        };
    }
});

// ===== Tool 3: kill_process =====
server.registerTool('kill_process', {
    title: 'Kill Process by Port',
    description: 'Kill the process occupying a specific port.',
    inputSchema: z.object({
        port: z.number().int().min(1).max(65535).describe('Port number to free up'),
        force: z.boolean().default(true).describe('Force kill (SIGKILL / taskkill /F)'),
    }),
}, async ({ port, force }) => {
    try {
        const isFree = await isPortFree(port);
        if (isFree) {
            return {
                content: [{
                        type: 'text',
                        text: JSON.stringify({ success: false, message: `Port ${port} is not in use` }, null, 2),
                    }],
                isError: true,
            };
        }
        const processInfo = await findProcessByPort(port);
        if (!processInfo) {
            return {
                content: [{
                        type: 'text',
                        text: JSON.stringify({ success: false, message: `Could not find process on port ${port}` }, null, 2),
                    }],
                isError: true,
            };
        }
        await killProcessByPid(processInfo.pid, force);
        const stillInUse = !await isPortFree(port);
        return {
            content: [{
                    type: 'text',
                    text: JSON.stringify({
                        success: !stillInUse,
                        killed_pid: processInfo.pid,
                        killed_name: processInfo.name,
                        port,
                        message: stillInUse ? 'Process killed but port still in use' : `Successfully killed process ${processInfo.pid} (${processInfo.name}) on port ${port}`,
                    }, null, 2),
                }],
        };
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return {
            content: [{ type: 'text', text: JSON.stringify({ error: true, message }, null, 2) }],
            isError: true,
        };
    }
});

// ===== Tool 4: network_system_view (this fork) =====
server.registerTool('network_system_view', {
    title: 'Network System View',
    description: 'One-call snapshot of the network + system state: host identity, interface addresses, '
        + 'listening TCP ports with owning processes, TCP connection states, default route/gateway and DNS '
        + 'resolvers. Use target="wsl" to look at the Ubuntu WSL distro instead of the Windows host.',
    inputSchema: z.object({
        target: z.enum(['host', 'wsl']).default('host')
            .describe('"host" = where this server runs (Windows); "wsl" = the Ubuntu WSL distro'),
        include: z.array(z.enum(['system', 'interfaces', 'listening', 'connections', 'routes', 'dns']))
            .default(['system', 'interfaces', 'listening', 'connections', 'routes', 'dns'])
            .describe('Which sections to collect'),
    }),
}, async ({ target, include }) => {
    try {
        const want = new Set(include);
        const view = {
            target,
            collected_at: new Date().toISOString(),
        };
        if (want.has('system')) view.system = await collectSystem(target);
        if (want.has('interfaces')) view.interfaces = await collectInterfaces(target);
        if (want.has('listening')) {
            const listening = await collectListening(target);
            listening.sort((a, b) => a.port - b.port);
            view.listening = listening;
            view.listening_count = listening.length;
            view.listening_processes = [...new Set(listening.map((l) => l.process))]
                .filter((p) => p && p !== 'unknown').sort();
        }
        if (want.has('connections')) {
            view.connection_states = await collectConnectionStates(target);
        }
        if (want.has('routes')) view.routes = await collectRoutes(target);
        if (want.has('dns')) view.dns_servers = await collectDns(target);
        return {
            content: [{ type: 'text', text: JSON.stringify(view, null, 2) }],
        };
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return {
            content: [{ type: 'text', text: JSON.stringify({ error: true, message }, null, 2) }],
            isError: true,
        };
    }
});

// ============================================================
// Start
// ============================================================
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('port-manager-mcp (local fork) server running on stdio');
}
main().catch((error) => {
    console.error('Fatal error:', error);
    process.exit(1);
});
process.on('SIGINT', async () => {
    await server.close();
    process.exit(0);
});
