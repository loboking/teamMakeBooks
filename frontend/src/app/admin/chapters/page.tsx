"use client";

import { useState, useEffect } from "react";
import { useAdminWork } from "@/lib/admin";
import ChapterTable from "@/components/admin/ChapterTable";


type Chapter = {
  n: number;
  title: string;
  status: string;
  published: boolean;
  created_at: string;
};

export default function ChaptersPage() {
  const { selectedWork } = useAdminWork();
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchChapters();
  }, []);

  const fetchChapters = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/works/${selectedWork}/chapters`);
      if (res.ok) {
        const data = await res.json();
        setChapters(data);
      }
    } catch (e) {
      console.error("Failed to fetch chapters:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <ChapterTable chapters={chapters} onRefresh={fetchChapters} />
      )}
    </div>
  );
}
