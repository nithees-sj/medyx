// Copies the PDF.js worker that react-pdf needs into /public, so it is served same-origin.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const pdfjsDir = path.dirname(require.resolve("pdfjs-dist/package.json", { paths: [require.resolve("react-pdf")] }));
const src = path.join(pdfjsDir, "build", "pdf.worker.min.mjs");
const dest = path.join(process.cwd(), "public", "pdf.worker.min.mjs");
if (!existsSync(path.dirname(dest))) mkdirSync(path.dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log(`copied ${path.relative(process.cwd(), src)} → public/pdf.worker.min.mjs`);
