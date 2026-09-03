// The one lint that matters here: is anything USED that was never defined or imported?
// A missing import is invisible to pytest and to esbuild (it bundles happily) and lands as
// "ReferenceError: isGeneralKind is not defined" on a blank page (the owner, 2026-09-03).
//   cd website && npx eslint -c eslint.undef.mjs -f json src/*.jsx src/*.js
// One question only: is anything used that was never defined or imported? (no-undef)
export default [
  { files: ["**/*.jsx", "**/*.js"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: Object.fromEntries(("window document navigator console setTimeout clearTimeout setInterval clearInterval "
        + "fetch localStorage sessionStorage location history alert confirm prompt requestAnimationFrame "
        + "cancelAnimationFrame ResizeObserver IntersectionObserver MutationObserver WebSocket URL URLSearchParams "
        + "Blob File FileReader FormData Image Audio AbortController Event CustomEvent KeyboardEvent MouseEvent "
        + "SpeechSynthesisUtterance speechSynthesis matchMedia getComputedStyle performance crypto atob btoa "
        + "process Buffer __dirname require module exports globalThis structuredClone queueMicrotask "
        + "HTMLElement Node Text DOMParser XMLHttpRequest EventSource Notification navigator screen "
        + "TextDecoder TextEncoder MediaRecorder addEventListener removeEventListener dispatchEvent "
        + "React JSX").split(" ").filter(Boolean).map((k) => [k, "readonly"])) },
    rules: { "no-undef": "error" } },
];
