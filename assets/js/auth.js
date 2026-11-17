import { supabase } from './supabase.js';

// Send the visitor to the login page unless an operator session exists.
// Protection of the data itself is row-level security; this only avoids an empty page.
export async function requireOperator() {
  const { data } = await supabase.auth.getSession();
  const session = data.session;
  if (!session) {
    window.location.replace('login.html');
    return null;
  }
  const role = session.user?.app_metadata?.role;
  if (role !== 'admin') {
    await supabase.auth.signOut();
    window.location.replace('login.html?denied=1');
    return null;
  }
  return session;
}

export async function signIn(email, password) {
  return supabase.auth.signInWithPassword({ email, password });
}

export async function signOut() {
  await supabase.auth.signOut();
  window.location.replace('login.html');
}
