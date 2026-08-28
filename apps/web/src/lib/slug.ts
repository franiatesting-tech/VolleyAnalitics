/** Turns an organization name into a URL-safe slug fragment (lowercase,
 * ascii, hyphen-separated, no leading/trailing hyphens). Better Auth
 * requires a unique slug per organization, so callers append a random
 * suffix -- this only normalizes the human-readable part. */
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}
