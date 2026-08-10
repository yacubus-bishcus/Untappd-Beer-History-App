export type BeerCheckin = {
  id: number;
  user_id: string;
  fingerprint: string;
  beer_name: string;
  producer: string | null;
  consumed_location: string | null;
  latitude: number | null;
  longitude: number | null;
  beer_type: string | null;
  my_rating: number | null;
  global_rating: number | null;
  checked_in_at: string | null;
  total_checkins: number | null;
  imported_at: string;
};

export type ImportResult = {
  received: number;
  synced: number;
  skipped: number;
  parseWarnings: number;
  libraryTotal: number;
};
