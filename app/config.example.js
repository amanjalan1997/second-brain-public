// Copy to config.js and fill in from Supabase → Project Settings → API.
// The anon key is Supabase's public key: the owner-only rule in supabase/schema.sql is what keeps the data private.
// The secret service key lives only in .env and must never go here.
window.SECOND_BRAIN_CONFIG = {
  supabaseUrl: "https://<SUPABASE_REF>.supabase.co",
  supabaseAnonKey: "<anon key>",
  ownerEmail: "you@example.edu",
};
