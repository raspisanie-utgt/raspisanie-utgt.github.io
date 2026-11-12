# Appearance effects

The appearance dialog stores its own preferences in `utgt-appearance-v1`. Effects are off by default. The existing theme keeps its own storage and control. Reduced motion disables moving particles and snow shedding while allowing a static atmosphere or holiday decoration.

`site/appearance-rules.js` contains season boundaries and the holiday calendar. To add a holiday, add its ID, Russian label, inclusive `MM-DD` display window, priority, and two small symbols. Windows can cross New Year. The highest priority wins and ties follow list order. The UI shows the active label in the appearance dialog. Keep holiday art sparse and use static symbols on solemn dates.

For a new effect, add its ID to the rules that select it. For a manual choice, also add the ID to `manualEffects` and add its Russian option in `site/index.html`. Configure its particle shape or static treatment in `site/appearance-renderer.js`. Keep the 30 FPS limit, canvas pixel budget, particle caps and five-pixel snow cap. Snow uses one canvas and tracks visible edges. Click and details events remove part of the affected pile.

Weather mode uses [Open-Meteo](https://open-meteo.com/en/docs) at fixed coordinates for the [college in Ukhta](https://utgt-pgups.ru/sveden/common/). The cache lasts 30 minutes, a failed request waits five minutes before retrying, and offline or unavailable weather uses Moscow-calendar seasonal effects. The service worker precaches the versioned appearance assets with the existing application assets.

Run `node --test tests/*.test.js` and `bash tests/browser/run.sh 13`. The browser check also runs in the nightly suite.
