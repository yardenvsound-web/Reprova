// Public configuration only. The Supabase anon key is meant to be public:
// it is protected by row-level security. Never put any other key here.
export const SUPABASE_URL = 'https://wnqxqtbmadoetwwyceun.supabase.co';
export const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InducXhxdGJtYWRvZXR3d3ljZXVuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ3NzA5ODksImV4cCI6MjExMDM0Njk4OX0.5m4BLR9N4Rdp-ElQs-0pHw_EbWT4LnLyC8Tdhl5zqwE';

// The runner is shown as offline when its heartbeat is older than this.
export const RUNNER_STALE_SECONDS = 120;
// How often the Dashboard refreshes (no realtime in the course stack).
export const REFRESH_SECONDS = 15;
