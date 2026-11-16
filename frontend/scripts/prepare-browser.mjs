/** Package the single-thread engine and OFL font for same-origin static hosting. */
import { mkdir, copyFile, readdir, readFile, writeFile, access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const destination = path.join(root, "public", "ffmpeg");
await mkdir(destination, { recursive: true });
const core = path.join(root, "node_modules", "@ffmpeg", "core");
const wrapper = path.join(root, "node_modules", "@ffmpeg", "ffmpeg");
for (const name of ["ffmpeg-core.js", "ffmpeg-core.wasm"]) await copyFile(path.join(core, "dist", "esm", name), path.join(destination, name));
for (const name of await readdir(path.join(wrapper, "dist", "esm"))) if (name.endsWith(".js")) await copyFile(path.join(wrapper, "dist", "esm", name), path.join(destination, name));

async function download(url, target) {
  try { await access(target); return; } catch { /* Download only missing build assets. */ }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Unable to package browser caption font (${response.status}).`);
  await writeFile(target, new Uint8Array(await response.arrayBuffer()));
}
await download("https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf", path.join(destination, "NotoSans.ttf"));
await download("https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/OFL.txt", path.join(destination, "FONT-LICENSE.txt"));
await writeFile(path.join(destination, "LICENSES.txt"), `FFmpeg WebAssembly core: GPL-2.0-or-later. Source and build instructions: https://github.com/ffmpegwasm/ffmpeg.wasm/tree/main/packages/core\nFFmpeg wrapper: MIT. Source: https://github.com/ffmpegwasm/ffmpeg.wasm/tree/main/packages/ffmpeg\nFFmpeg source: https://ffmpeg.org/download.html\nNoto Sans font: SIL Open Font License 1.1. See FONT-LICENSE.txt and https://github.com/google/fonts/tree/main/ofl/notosans\n\nPackaged versions:\n${await readFile(path.join(core, "package.json"), "utf8")}\n`);
console.log("Packaged same-origin, single-thread browser FFmpeg engine and open-license caption font.");
