// quick stdio smoke test for the local port-manager-mcp fork
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const transport = new StdioClientTransport({
  command: 'node',
  args: ['C:\\Users\\0501JP\\mppdp5\\port-manager-mcp\\index.js'],
});
const client = new Client({ name: 'smoke', version: '1.0.0' });
await client.connect(transport);

const tools = await client.listTools();
console.log('TOOLS:', tools.tools.map((t) => t.name).join(', '));

const res = await client.callTool({ name: 'network_system_view', arguments: { target: 'host', include: ['system', 'interfaces', 'listening', 'connections', 'routes', 'dns'] } });
const text = res.content?.[0]?.text ?? '';
const view = JSON.parse(text);
console.log('hostname      :', view.system?.hostname);
console.log('platform      :', view.system?.platform, view.system?.release);
console.log('interfaces    :', (view.interfaces ?? []).length);
console.log('listening     :', view.listening_count);
console.log('listen procs  :', (view.listening_processes ?? []).slice(0, 12).join(', '));
console.log('conn states   :', JSON.stringify(view.connection_states));
console.log('gateway       :', view.routes?.default_gateway);
console.log('dns           :', (view.dns_servers ?? []).join(', '));

const wsl = await client.callTool({ name: 'network_system_view', arguments: { target: 'wsl', include: ['system', 'listening', 'routes', 'dns'] } });
const w = JSON.parse(wsl.content?.[0]?.text ?? '{}');
console.log('--- wsl ---');
console.log('hostname      :', w.system?.hostname);
console.log('listening     :', w.listening_count);
console.log('gateway       :', w.routes?.default_gateway);
console.log('dns           :', (w.dns_servers ?? []).join(', '));

await client.close();
