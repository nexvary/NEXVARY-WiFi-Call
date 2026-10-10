# Local QR encoder

Project Nayuki QR Code generator library, MIT license.

Official source: https://github.com/nayuki/QR-Code-generator

Pinned revision: `3c6d0b3cefb4e049dc337e82237c9644399716a8`.
Source path: `typescript-javascript/qrcodegen.ts`.
Upstream Git blob: `c4191ac0b5f8a24d87fd9340ceaa2d3b07d0231a`.

Vendored source SHA-256: `e332e4ab0c2530fdd5a412387c389385b51592701ae7b04abdd948bb44976fa0`.
Compiled `qrcodegen.js` SHA-256: `79f419f267ce5a80d97f8099e0a789a4ecc4697b5348d86371a1f3b2a75d6e03`.

The unmodified TypeScript source is retained in `vendor/qrcodegen.ts`. Its full MIT copyright, permission and warranty notice is retained in that file and the compiled JavaScript. Both source and notice were inspected before adoption. No QR service or CDN receives pairing codes.

Reproduce the JavaScript with TypeScript 5.7.3:

```bash
tsc server/panel/vendor/qrcodegen.ts --target ES2017 --lib ES2017,DOM --outFile server/panel/qrcodegen.js
```

Compilation is a development step. Running or installing the panel requires only the bundled JavaScript and Python standard library; no npm dependency is installed on the server.
