import { createHash } from "node:crypto";

import Papa from "papaparse";
import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

const MAX_FILE_SIZE = 5 * 1024 * 1024;
const UPSERT_SIZE = 500;
const REQUIRED_COLUMNS = [
  "Beer Name",
  "Producer",
  "Consumed Location",
  "Lat",
  "Long",
  "Beer Type",
  "My Rating",
  "Global Rating",
  "Recent Date",
];

type CsvRow = Record<string, string | undefined>;

function clean(value: string | undefined) {
  const trimmed = String(value ?? "").trim();
  return trimmed || null;
}

function numberOrNull(value: string | undefined) {
  const normalized = String(value ?? "").replaceAll(",", "").trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function dateOrNull(value: string | undefined) {
  const normalized = String(value ?? "").trim();
  if (!normalized) return null;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.valueOf()) ? null : parsed.toISOString();
}

function fingerprint(row: CsvRow, checkedInAt: string | null) {
  const primaryIdentity = [
    clean(row["Beer Name"])?.toLocaleLowerCase(),
    clean(row.Producer)?.toLocaleLowerCase(),
    checkedInAt,
  ];
  const fallbackIdentity = checkedInAt
    ? []
    : [
        clean(row["Consumed Location"])?.toLocaleLowerCase(),
        clean(row["Beer Type"])?.toLocaleLowerCase(),
        clean(row["My Rating"]),
        clean(row["Global Rating"]),
      ];

  return createHash("sha256")
    .update([...primaryIdentity, ...fallbackIdentity].join("|"))
    .digest("hex");
}

function errorResponse(message: string, status: number) {
  return NextResponse.json({ error: message }, { status });
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: authData, error: authError } = await supabase.auth.getClaims();
  const userId = authData?.claims?.sub;

  if (authError || !userId) {
    return errorResponse("Sign in before importing a beer history.", 401);
  }

  const formData = await request.formData();
  const file = formData.get("file");

  if (!(file instanceof File)) {
    return errorResponse("Choose a CSV file to import.", 400);
  }

  if (!file.name.toLowerCase().endsWith(".csv")) {
    return errorResponse("The selected file must be a .csv export.", 400);
  }

  if (file.size > MAX_FILE_SIZE) {
    return errorResponse("The CSV is larger than the 5 MB import limit.", 413);
  }

  const csv = await file.text();
  const parsed = Papa.parse<CsvRow>(csv, {
    header: true,
    skipEmptyLines: "greedy",
    transformHeader: (header) => header.replace(/^\uFEFF/, "").trim(),
  });

  const headers = parsed.meta.fields ?? [];
  const missingColumns = REQUIRED_COLUMNS.filter((column) => !headers.includes(column));

  if (missingColumns.length) {
    return errorResponse(
      `This does not look like an Untappd Beer History export. Missing: ${missingColumns.join(", ")}.`,
      400,
    );
  }

  const skipped: number[] = [];
  const rows = parsed.data.flatMap((row, index) => {
    const beerName = clean(row["Beer Name"]);
    if (!beerName) {
      skipped.push(index);
      return [];
    }

    const checkedInAt = dateOrNull(row["Recent Date"]);
    return [
      {
        user_id: userId,
        fingerprint: fingerprint(row, checkedInAt),
        beer_name: beerName,
        producer: clean(row.Producer),
        consumed_location: clean(row["Consumed Location"]),
        latitude: numberOrNull(row.Lat),
        longitude: numberOrNull(row.Long),
        beer_type: clean(row["Beer Type"]),
        my_rating: numberOrNull(row["My Rating"]),
        global_rating: numberOrNull(row["Global Rating"]),
        checked_in_at: checkedInAt,
        total_checkins: numberOrNull(row["Total Checkins"] ?? row.total_checkins),
        imported_at: new Date().toISOString(),
      },
    ];
  });

  if (!rows.length) {
    return errorResponse("No valid beer rows were found in the CSV.", 400);
  }

  for (let start = 0; start < rows.length; start += UPSERT_SIZE) {
    const batch = rows.slice(start, start + UPSERT_SIZE);
    const { error } = await supabase.from("beer_checkins").upsert(batch, {
      onConflict: "user_id,fingerprint",
    });

    if (error) {
      return errorResponse(`The import could not be saved: ${error.message}`, 500);
    }
  }

  const { count, error: countError } = await supabase
    .from("beer_checkins")
    .select("id", { count: "exact", head: true });

  if (countError) {
    return errorResponse(
      "Your beers were saved, but the updated library total could not be loaded.",
      500,
    );
  }

  return NextResponse.json({
    received: parsed.data.length,
    synced: rows.length,
    skipped: skipped.length,
    parseWarnings: parsed.errors.length,
    libraryTotal: count ?? rows.length,
  });
}
