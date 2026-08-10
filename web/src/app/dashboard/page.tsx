import { redirect } from "next/navigation";

import { Dashboard } from "@/components/dashboard";
import { getBeerCheckins } from "@/lib/beer-data";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();
  const userId = data?.claims?.sub;

  if (error || !userId) {
    redirect("/login");
  }

  const checkins = await getBeerCheckins(supabase);
  const email =
    typeof data.claims.email === "string" ? data.claims.email : "Beer explorer";

  return <Dashboard checkins={checkins} email={email} />;
}
