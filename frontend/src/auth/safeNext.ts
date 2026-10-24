/**
 * Where to go after signing in: only a path on this site, never another site
 * (the same rule the server applies to SSO redirects).
 */
export function safeNext(target: string | null | undefined): string {
  if (
    !target ||
    target.length > 2048 ||
    !target.startsWith('/') ||
    target.startsWith('//') ||
    target.includes('\\') ||
    // eslint-disable-next-line no-control-regex
    /[\u0000-\u001f]/.test(target)
  ) {
    return '/';
  }
  return target;
}
