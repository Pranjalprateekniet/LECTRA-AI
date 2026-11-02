import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test("Route separation: / and /admin pages exist as distinct Next.js routes", () => {
  const userPagePath = path.resolve(__dirname, "../src/app/page.tsx");
  const adminPagePath = path.resolve(__dirname, "../src/app/admin/page.tsx");

  assert.equal(fs.existsSync(userPagePath), true, "User page route / must exist");
  assert.equal(fs.existsSync(adminPagePath), true, "Admin page route /admin must exist");
});

test("User page (/) does not import or render ingestion controls", () => {
  const userPageContent = fs.readFileSync(
    path.resolve(__dirname, "../src/app/page.tsx"),
    "utf-8"
  );

  // User page should only import ChatInterface and Header
  assert.equal(userPageContent.includes("ChatInterface"), true);
  assert.equal(userPageContent.includes("Header"), true);

  // User page must NOT import or reference ingestion components
  assert.equal(userPageContent.includes("PlaylistSubmitForm"), false);
  assert.equal(userPageContent.includes("PlaylistProgressBar"), false);
  assert.equal(userPageContent.includes("VideoProcessingTable"), false);
  assert.equal(userPageContent.includes("ActivityLog"), false);
  assert.equal(userPageContent.includes("VectorIndexStatus"), false);
  assert.equal(userPageContent.includes("isAdmin={true}"), false);
  assert.equal(userPageContent.includes('href="/admin"'), false);
});

test("Admin page (/admin) imports all 5 required administration modules", () => {
  const adminPageContent = fs.readFileSync(
    path.resolve(__dirname, "../src/app/admin/page.tsx"),
    "utf-8"
  );

  // 1. Playlist Management
  assert.equal(adminPageContent.includes("PlaylistSubmitForm"), true);
  assert.equal(adminPageContent.includes("PlaylistSelector"), true);

  // 2. Ingestion Dashboard
  assert.equal(adminPageContent.includes("PlaylistProgressBar"), true);

  // 3. Video Processing Statistics
  assert.equal(adminPageContent.includes("StatisticsDashboard"), true);
  assert.equal(adminPageContent.includes("VideoProcessingTable"), true);

  // 4. Ingestion Logs
  assert.equal(adminPageContent.includes("ActivityLog"), true);

  // 5. Vector Index Status
  assert.equal(adminPageContent.includes("VectorIndexStatus"), true);

  // Header configured with admin mode
  assert.equal(adminPageContent.includes("isAdmin={true}"), true);
});

test("Header component does not expose links to /admin on normal user view", () => {
  const headerContent = fs.readFileSync(
    path.resolve(__dirname, "../src/components/Header.tsx"),
    "utf-8"
  );

  // Does not have hardcoded navigation tabs to admin
  assert.equal(headerContent.includes('href="/admin"'), false);
  assert.equal(headerContent.includes("Tab 1: Data Ingestion"), false);
});

