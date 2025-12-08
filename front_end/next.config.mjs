import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import { fileURLToPath } from 'url';


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..'); 
const configPath = path.join(rootDir, 'configs', 'magnus_config.yaml');
const fileContents = fs.readFileSync(configPath, 'utf8');
const magnusConfig = yaml.load(fileContents);


/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    SERVER_PORT: magnusConfig.server.port.toString(),
  }
};


export default nextConfig;