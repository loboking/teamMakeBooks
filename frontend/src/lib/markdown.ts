// Minimal markdown utility — actual rendering uses react-markdown in components
// This file exists for any string-level preprocessing if needed.

export function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/^\s*>\s*/gm, "")
    .trim();
}
