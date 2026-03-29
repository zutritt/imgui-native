import { createRequire } from 'node:module';
import { platform, arch } from 'node:process';
import { join } from 'node:path';
import { existsSync } from 'node:fs';

const require = createRequire(import.meta.url);

function getBinaryPath() {
  const localBuild = join(import.meta.dirname, '..', 'build', 'Release', 'imgui.node');

  if (existsSync(localBuild)) {
    return localBuild;
  }

  const prebuild = join(import.meta.dirname, '..', 'prebuild', `${platform}-${arch}`, 'imgui.node');

  if (existsSync(prebuild)) {
    return prebuild;
  }

  throw new Error(`No prebuild binary found for platform ${platform}-${arch}, and no local build found.`);
}

const addon = require(getBinaryPath());
export default addon;
