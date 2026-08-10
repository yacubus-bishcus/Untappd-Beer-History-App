import type { SupabaseClient } from "@supabase/supabase-js";

import type { BeerCheckin } from "@/lib/types";

const PAGE_SIZE = 1000;

export async function getBeerCheckins(supabase: SupabaseClient) {
  const firstPage = await supabase
    .from("beer_checkins")
    .select("*", { count: "exact" })
    .order("checked_in_at", { ascending: false, nullsFirst: false })
    .range(0, PAGE_SIZE - 1);

  if (firstPage.error) {
    throw new Error(`Could not load beer history: ${firstPage.error.message}`);
  }

  const total = firstPage.count ?? firstPage.data.length;
  if (total <= PAGE_SIZE) {
    return firstPage.data as BeerCheckin[];
  }

  const pageStarts = Array.from(
    { length: Math.ceil(total / PAGE_SIZE) - 1 },
    (_, index) => (index + 1) * PAGE_SIZE,
  );

  const remainingPages = await Promise.all(
    pageStarts.map((start) =>
      supabase
        .from("beer_checkins")
        .select("*")
        .order("checked_in_at", { ascending: false, nullsFirst: false })
        .range(start, start + PAGE_SIZE - 1),
    ),
  );

  const pageError = remainingPages.find((page) => page.error)?.error;
  if (pageError) {
    throw new Error(`Could not load all beer history: ${pageError.message}`);
  }

  return [
    ...firstPage.data,
    ...remainingPages.flatMap((page) => page.data ?? []),
  ] as BeerCheckin[];
}
