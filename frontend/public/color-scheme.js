// Applies the saved or system colour scheme before the app loads, so dark-theme users
// see no flash of the light theme. Same storage key and attribute as Mantine. A file,
// not an inline script, so a strict Content-Security-Policy can allow it.
(function () {
  var scheme = 'light';
  try {
    var saved = window.localStorage.getItem('mantine-color-scheme-value');
    if (saved === 'light' || saved === 'dark') scheme = saved;
    else if (window.matchMedia('(prefers-color-scheme: dark)').matches) scheme = 'dark';
  } catch (e) {
    // Storage blocked: keep the light theme until the app starts.
  }
  document.documentElement.setAttribute('data-mantine-color-scheme', scheme);
})();
