import { existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@rsbuild/core';
import { pluginReact } from '@rsbuild/plugin-react';
import { RsdoctorRspackPlugin } from '@rsdoctor/rspack-plugin';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const useRsdoctor = process.env.RSDOCTOR === 'true';

/**
 * Local x86_64 wasm-pack output (`molrs-wasm/.x86_64`) wins when present so
 * a sibling checkout can ship unreleased parsers. CI / publish have no
 * sibling tree, so they resolve the npm package (latest published).
 */
const resolveMolrs = (): string => {
  const local = path.resolve(__dirname, '../../../molrs/molrs-wasm/.x86_64');
  if (existsSync(path.join(local, 'package.json'))) {
    return local;
  }
  return path.dirname(createRequire(import.meta.url).resolve('@molcrafts/molrs/package.json'));
};

// Docs: https://rsbuild.rs/config/
export default defineConfig(({ command }) => {
  const useMock = command === 'dev' && process.env.MOLAB_USE_MOCK === 'true';

  return {
    plugins: [pluginReact()],
    resolve: {
      alias: {
        '@molcrafts/molrs': resolveMolrs(),
        '@schemas': path.resolve(__dirname, '../../src/molab/schemas'),
        '@molcrafts/molab-plugin/ui': path.resolve(__dirname, '../plugin/src/ui'),
        '@molcrafts/molab-plugin/testing': path.resolve(__dirname, '../plugin/src/testing.ts'),
        '@molcrafts/molab-plugin/externals': path.resolve(__dirname, '../plugin/src/externals.ts'),
        '@molcrafts/molab-plugin': path.resolve(__dirname, '../plugin/src'),
      },
    },
    tools: {
      // flowgram's free-layout-editor uses inversify DI, which relies on legacy
      // (stage-2) decorators + emitted decorator metadata at runtime. Enable the
      // SWC transforms so the canvas core's DI wiring resolves in the bundle.
      swc: {
        jsc: {
          parser: {
            syntax: 'typescript',
            tsx: true,
            decorators: true,
          },
          transform: {
            legacyDecorator: true,
            decoratorMetadata: true,
          },
        },
      },
      rspack: {
        // ``@molcrafts/molrs`` is a wasm-pack *bundler*-target package: its JS
        // does ``import * as wasm from "./molrs_bg.wasm"``. Without WebAssembly
        // module support rspack leaves that import undefined, so molvis-core's
        // ``Frame.frame_new`` is missing and trajectory rendering crashes.
        experiments: { asyncWebAssembly: true },
        plugins: [
          ...(useRsdoctor
            ? [
                new RsdoctorRspackPlugin({
                  disableClientServer: true,
                  output: {
                    mode: 'brief',
                    options: { type: ['json'] },
                  },
                }),
              ]
            : []),
        ],
      },
    },
    splitChunks: {
      cacheGroups: {
        markdown: {
          test: /[\\/]node_modules[\\/](?:katex|rehype-katex|remark-math|remark-gfm|react-markdown|micromark|mdast-|hast-|unified|vfile|property-information)[\\/]/,
          name: 'lib-markdown',
          chunks: 'async',
          priority: 30,
        },
        molrs: {
          test: /[\\/](?:node_modules[\\/]@molcrafts[\\/]molrs|molrs[\\/]molrs-wasm)[\\/]/,
          name: 'lib-molrs',
          chunks: 'async',
          priority: 30,
        },
        babylon: {
          test: /[\\/]node_modules[\\/]@babylonjs[\\/]/,
          name: 'lib-babylon',
          chunks: 'async',
          priority: 30,
        },
        vega: {
          test: /[\\/]node_modules[\\/](?:vega|vega-lite|vega-embed)[\\/]/,
          name: 'lib-vega',
          chunks: 'async',
          priority: 20,
        },
        flowgram: {
          test: /[\\/]node_modules[\\/]@flowgram\.ai[\\/]/,
          name: 'lib-flowgram',
          chunks: 'async',
          priority: 20,
        },
        milkdown: {
          test: /[\\/]node_modules[\\/](?:@milkdown|prosemirror-)[\\/]/,
          name: 'lib-milkdown',
          chunks: 'async',
          priority: 20,
        },
        monaco: {
          test: /[\\/]node_modules[\\/](?:monaco-editor|@monaco-editor)[\\/]/,
          name: 'lib-monaco',
          chunks: 'async',
          priority: 20,
        },
        radix: {
          test: /[\\/]node_modules[\\/]@radix-ui[\\/]/,
          name: 'lib-radix',
          chunks: 'all',
          priority: 10,
        },
      },
    },
    source: {
      define: {
        __USE_MOCK__: useMock,
      },
    },
    server: {
      // Mock mode is self-contained. Leaving the Python proxy enabled there
      // turns any intentionally unimplemented fixture into a noisy HPM
      // connection error when no backend is running.
      proxy: useMock
        ? {}
        : {
            // API target for `npm run dev:api` / `molab serve --dev`.
            // Prefer MOLAB_API_PORT (set by the Python CLI); do not pass
            // --api-port on the rsbuild argv — CAC rejects unknown options.
            '/api': {
              target: `http://localhost:${process.env.MOLAB_API_PORT || '8000'}`,
              changeOrigin: true,
              // Soft remote (503 needs_auth) is a normal JSON body — do not
              // log HPM connection errors for closed idle sockets.
              onError(err, _req, res) {
                // Only surface real proxy death; ignore ECONNRESET/EPIPE noise.
                const code = (err as NodeJS.ErrnoException)?.code;
                if (code === "ECONNRESET" || code === "EPIPE" || code === "ECONNREFUSED") {
                  if (res && !res.headersSent) {
                    res.writeHead(503, { "Content-Type": "application/json" });
                    res.end(JSON.stringify({ error: { code: "BACKEND", message: "offline" } }));
                  }
                  return;
                }
                console.warn("[proxy]", code || err.message);
              },
            },
          },
    },
  };
});
