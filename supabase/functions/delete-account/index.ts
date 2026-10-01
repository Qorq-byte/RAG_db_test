import { withSupabase } from "npm:@supabase/server@1";

// Only a signed-in user who can also read a fresh email code may delete an account.
// The admin client and its secret stay inside the Supabase Edge Function runtime.
export default {
  fetch: withSupabase({ auth: "user" }, async (request, context) => {
    if (request.method !== "POST") {
      return Response.json({ error: "method_not_allowed" }, { status: 405 });
    }

    const claims = context.jwtClaims as { sub?: string; email?: string };
    if (!claims.sub || !claims.email) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }

    let code: unknown;
    try {
      ({ code } = await request.json());
    } catch {
      return Response.json({ error: "invalid_request" }, { status: 400 });
    }
    if (typeof code !== "string" || !/^[0-9]{6,32}$/.test(code)) {
      return Response.json({ error: "invalid_code" }, { status: 400 });
    }

    const { data: verified, error: verifyError } = await context.supabase.auth.verifyOtp({
      email: claims.email,
      token: code,
      type: "email",
    });
    if (verifyError || verified.user?.id !== claims.sub) {
      return Response.json({ error: "verification_failed" }, { status: 403 });
    }

    const { error: deleteError } = await context.supabaseAdmin.auth.admin.deleteUser(
      claims.sub,
    );
    if (deleteError) {
      return Response.json({ error: "delete_failed" }, { status: 503 });
    }
    return Response.json({ deleted: true });
  }),
};
