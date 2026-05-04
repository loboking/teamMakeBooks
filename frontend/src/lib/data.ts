import fs from "fs";
import path from "path";
import yaml from "js-yaml";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const NOVELS_DIR = path.join(PROJECT_ROOT, "novels");
const AUTHORS_DIR = path.join(PROJECT_ROOT, "authors");

export type WorkSummary = {
  workId: string;
  title: string;
  genre: string;
  authorId: string;
  isAiPersona: boolean;
  copyright: string;
  publishedChapters: number;
};

export type AuthorPersona = {
  id: string;
  name: string;
  genre: string;
  style: string;
  tone: string;
};

export type WorkDetail = WorkSummary & {
  author: AuthorPersona;
};

export type ChapterSummary = {
  n: number;
  title: string;
  tags: string[];
  oneLineSummary: string;
  publishedAt: string;
};

export type ChapterContent = {
  meta: ChapterSummary;
  body: string;
};

function readJsonSafe<T>(filePath: string): T | null {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function readFileSafe(filePath: string): string | null {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return null;
  }
}

function parseAuthor(authorId: string): AuthorPersona {
  const filePath = path.join(AUTHORS_DIR, `${authorId}.yaml`);
  const raw = readFileSafe(filePath);
  if (!raw) {
    return { id: authorId, name: authorId, genre: "", style: "", tone: "" };
  }
  const parsed = yaml.load(raw) as Record<string, string>;
  return {
    id: authorId,
    name: parsed.name ?? authorId,
    genre: parsed.genre ?? "",
    style: parsed.style ?? "",
    tone: parsed.tone ?? "",
  };
}

function parseChapterMeta(raw: Record<string, unknown>): ChapterSummary {
  return {
    n: (raw.chapter_n as number) ?? (raw.chapter as number) ?? 0,
    title: (raw.title as string) ?? "",
    tags: (raw.tags as string[]) ?? [],
    oneLineSummary: (raw.one_line_summary as string) ?? "",
    publishedAt: (raw.published_at as string) ?? "",
  };
}

export function listWorks(): WorkSummary[] {
  if (!fs.existsSync(NOVELS_DIR)) return [];
  const entries = fs.readdirSync(NOVELS_DIR, { withFileTypes: true });
  const works: WorkSummary[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const metaPath = path.join(NOVELS_DIR, entry.name, "meta.json");
    const raw = readJsonSafe<Record<string, unknown>>(metaPath);
    if (!raw) continue;
    works.push({
      workId: entry.name,
      title: (raw.title as string) ?? entry.name,
      genre: (raw.genre as string) ?? "",
      authorId: (raw.author_id as string) ?? "",
      isAiPersona: (raw.is_ai_persona as boolean) ?? false,
      copyright: (raw.copyright as string) ?? "",
      publishedChapters: (raw.published_chapters as number) ?? 0,
    });
  }
  return works;
}

export function getWork(workId: string): WorkDetail | null {
  const metaPath = path.join(NOVELS_DIR, workId, "meta.json");
  const raw = readJsonSafe<Record<string, unknown>>(metaPath);
  if (!raw) return null;
  const authorId = (raw.author_id as string) ?? "";
  return {
    workId,
    title: (raw.title as string) ?? workId,
    genre: (raw.genre as string) ?? "",
    authorId,
    isAiPersona: (raw.is_ai_persona as boolean) ?? false,
    copyright: (raw.copyright as string) ?? "",
    publishedChapters: (raw.published_chapters as number) ?? 0,
    author: parseAuthor(authorId),
  };
}

export function listChapters(workId: string): ChapterSummary[] {
  const chaptersDir = path.join(NOVELS_DIR, workId, "chapters");
  if (!fs.existsSync(chaptersDir)) return [];
  const files = fs.readdirSync(chaptersDir);
  const chapters: ChapterSummary[] = [];
  for (const file of files) {
    if (!file.match(/^ch\d+_meta\.json$/)) continue;
    const raw = readJsonSafe<Record<string, unknown>>(
      path.join(chaptersDir, file)
    );
    if (!raw) continue;
    chapters.push(parseChapterMeta(raw));
  }
  return chapters.sort((a, b) => a.n - b.n);
}

export function getChapter(
  workId: string,
  n: number
): ChapterContent | null {
  const chaptersDir = path.join(NOVELS_DIR, workId, "chapters");
  const chStr = String(n).padStart(3, "0");
  const metaPath = path.join(chaptersDir, `ch${chStr}_meta.json`);
  const bodyPath = path.join(chaptersDir, `ch${chStr}.md`);

  const rawMeta = readJsonSafe<Record<string, unknown>>(metaPath);
  const body = readFileSafe(bodyPath);

  if (!rawMeta || !body) return null;
  return {
    meta: parseChapterMeta(rawMeta),
    body,
  };
}
