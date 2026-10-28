#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import initSqlJs from "sql.js";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DB_PATH = process.env.MPPOSE_DB || path.join(__dirname, "../processing/MPPoseManga/data/mppose_manga.db");

const server = new Server(
  {
    name: "mppose-manga-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

let SQL;
let dbCache = null;

async function getDb() {
  if (dbCache) return dbCache;
  if (!SQL) {
    SQL = await initSqlJs();
  }
  if (!fs.existsSync(DB_PATH)) {
    throw new Error(`Database not found: ${DB_PATH}. Run the Processing sketch first to create it.`);
  }
  const fileBuffer = fs.readFileSync(DB_PATH);
  dbCache = new SQL.Database(fileBuffer);
  return dbCache;
}

function queryAll(db, sql, params = []) {
  const stmt = db.prepare(sql);
  if (params.length > 0) {
    stmt.bind(params);
  }
  const results = [];
  while (stmt.step()) {
    results.push(stmt.getAsObject());
  }
  stmt.free();
  return results;
}

function queryOne(db, sql, params = []) {
  const results = queryAll(db, sql, params);
  return results[0] || null;
}

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "list_sessions",
        description: "List all pose capture sessions",
        inputSchema: { type: "object", properties: {} },
      },
      {
        name: "get_session",
        description: "Get details of a specific session",
        inputSchema: {
          type: "object",
          properties: {
            session_id: { type: "number", description: "Session ID" },
          },
          required: ["session_id"],
        },
      },
      {
        name: "list_screenshots",
        description: "List all captured screenshots",
        inputSchema: {
          type: "object",
          properties: {
            session_id: { type: "number", description: "Filter by session ID (optional)" },
            limit: { type: "number", description: "Limit results (default: 50)" },
          },
        },
      },
      {
        name: "get_screenshot",
        description: "Get details of a specific screenshot",
        inputSchema: {
          type: "object",
          properties: {
            screenshot_id: { type: "number", description: "Screenshot ID" },
          },
          required: ["screenshot_id"],
        },
      },
      {
        name: "list_frames",
        description: "List frame records for a session",
        inputSchema: {
          type: "object",
          properties: {
            session_id: { type: "number", description: "Session ID" },
            limit: { type: "number", description: "Limit results (default: 100)" },
          },
          required: ["session_id"],
        },
      },
      {
        name: "get_stats",
        description: "Get overall statistics",
        inputSchema: { type: "object", properties: {} },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    const db = await getDb();

    if (name === "list_sessions") {
      const sessions = queryAll(db, `
        SELECT s.*, 
               (SELECT COUNT(*) FROM screenshots sc WHERE sc.session_id = s.id) as screenshot_count,
               (SELECT COUNT(*) FROM frames f WHERE f.session_id = s.id) as frame_count_recorded
        FROM sessions s
        ORDER BY s.id DESC
      `);
      return { content: [{ type: "text", text: JSON.stringify(sessions, null, 2) }] };
    }

    if (name === "get_session") {
      const session_id = args.session_id;
      const session = queryOne(db, "SELECT * FROM sessions WHERE id = ?", [session_id]);
      const screenshots = queryAll(db, "SELECT * FROM screenshots WHERE session_id = ? ORDER BY frame_idx", [session_id]);
      const poseFrames = queryOne(db, "SELECT COUNT(*) as count FROM frames WHERE session_id = ? AND has_pose = 1", [session_id]);
      const totalFrames = queryOne(db, "SELECT COUNT(*) as count FROM frames WHERE session_id = ?", [session_id]);
      return { content: [{ type: "text", text: JSON.stringify({ session, screenshots, poseFrames: poseFrames?.count || 0, totalFrames: totalFrames?.count || 0 }, null, 2) }] };
    }

    if (name === "list_screenshots") {
      const session_id = args.session_id;
      const limit = args.limit || 50;
      let sql = "SELECT * FROM screenshots";
      let params = [];
      if (session_id) {
        sql += " WHERE session_id = ?";
        params.push(session_id);
      }
      sql += " ORDER BY id DESC LIMIT ?";
      params.push(limit);
      const screenshots = queryAll(db, sql, params);
      return { content: [{ type: "text", text: JSON.stringify(screenshots, null, 2) }] };
    }

    if (name === "get_screenshot") {
      const screenshot_id = args.screenshot_id;
      const screenshot = queryOne(db, "SELECT * FROM screenshots WHERE id = ?", [screenshot_id]);
      return { content: [{ type: "text", text: JSON.stringify(screenshot, null, 2) }] };
    }

    if (name === "list_frames") {
      const session_id = args.session_id;
      const limit = args.limit || 100;
      const frames = queryAll(db, "SELECT * FROM frames WHERE session_id = ? ORDER BY frame_idx LIMIT ?", [session_id, limit]);
      return { content: [{ type: "text", text: JSON.stringify(frames, null, 2) }] };
    }

    if (name === "get_stats") {
      const sessions = queryOne(db, "SELECT COUNT(*) as count FROM sessions");
      const screenshots = queryOne(db, "SELECT COUNT(*) as count FROM screenshots");
      const frames = queryOne(db, "SELECT COUNT(*) as count FROM frames");
      const poseFrames = queryOne(db, "SELECT COUNT(*) as count FROM frames WHERE has_pose = 1");
      return { content: [{ type: "text", text: JSON.stringify({ totalSessions: sessions?.count || 0, totalScreenshots: screenshots?.count || 0, totalFrames: frames?.count || 0, framesWithPose: poseFrames?.count || 0 }, null, 2) }] };
    }

    throw new Error(`Unknown tool: ${name}`);
  } catch (error) {
    return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("MPPose Manga MCP server running on stdio");
