# Browser dependency maintenance

- `jquery/jquery.min.js`: official full jQuery 3.7.1 release from
  https://code.jquery.com/jquery-3.7.1.min.js (SHA-256
  `fc9a93dd241f6b045cbff0481cf4e1901becd0e12fb45166a8f17f95823f0b1a`).
- `bootstrap/*`: JavaScript distributions and source maps from the official
  `bootstrap@4.6.2` npm package (`dist/js`).

The Bootstrap entry in `../argon_js_merged.js` and the standalone unsubscribe
page use `bootstrap.bundle.min.js`. Its private Popper 1 implementation avoids
conflicting with the global Popper 2 used by Tippy. Keep both the standalone
vendor distributions and their matching merged-bundle segments synchronized.
Bootstrap 4 is end-of-life; this same-major maintenance update does not replace
a future Bootstrap 5 migration.

Compatibility checks (including both standalone and merged assets):

```sh
npm ci --prefix tests --ignore-scripts
npm test --prefix tests
```

Run these from the repository root. They use an isolated jsdom test dependency;
they do not install or run the legacy Gutenberg build toolchain.
