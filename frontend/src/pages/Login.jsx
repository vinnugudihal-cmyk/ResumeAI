import { useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import "./Login.css";
import { loginUser, registerUser } from "../services/api";
import { useSession } from "../services/sessionStore";

// Must match MIN_PASSWORD_LENGTH in the service, so the message the
// user reads before submitting is the same rule the server applies.
const MIN_PASSWORD_LENGTH = 8;

/*
 * There used to be a "Quick Demo Sign-in" button on this page,
 * hardcoded to demo@resumeai.dev / demo-resume-2026.
 *
 * Two reasons it had to go. It is a shared account whose password
 * is published in the client bundle, so anyone who opened the
 * source could sign in as somebody else. And it is a fake account:
 * the brief for this screen is real sign-in with real addresses.
 * A button that hands out a session by clicking it is the opposite
 * of authentication.
 */

/**
 * The show / hide glyphs, drawn rather than typed.
 *
 * These were the characters U+1F441 U+FE0F U+200D U+1F5E8 - an eye,
 * a variation selector, a zero-width joiner and an eye with a
 * slash. That sequence renders as an eye on some systems and as
 * nothing at all, or as a box, on others, and when it renders as
 * nothing the button is still there and still working: it just
 * looks like the field has no toggle, which reads as "I cannot see
 * my password" and is exactly the bug this replaces.
 *
 * Inline SVG inherits currentColor, so the icon follows the button
 * in every state without a second stylesheet rule.
 */
function EyeIcon() {
  return (
    <svg
      className="eye-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
      <circle cx="12" cy="12" r="2.8" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg
      className="eye-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M3 3l18 18" />
      <path d="M10.6 6.1A9.9 9.9 0 0112 6c6.4 0 10 6 10 6a17 17 0 01-3.3 4" />
      <path d="M6.3 8.2A16.7 16.7 0 002 12s3.6 6 10 6a9.7 9.7 0 004.2-.9" />
      <path d="M9.9 9.9a2.8 2.8 0 004 4" />
    </svg>
  );
}

function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh } = useSession();

  // Which form to open with.
  //
  // A link from the landing page can ask for the sign-up form
  // directly ("No account yet? Create one"), so the starting mode
  // is read from the navigation state rather than always being
  // sign-in. The landing page sends `mode: "register"` for exactly
  // this reason.
  const [mode, setMode] = useState(
    location.state?.mode === "register" ? "register" : "login"
  );

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const isRegister = mode === "register";

  const saveUser = (user) => {
    if (!user) return;

    try {
      localStorage.setItem(
        "resumeai_user",
        JSON.stringify({
          name: user.name,
          email: user.email,
          loggedInAt: new Date().toISOString(),
        })
      );
    } catch (err) {
      console.warn("Could not cache the profile", err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    setError("");

    // Read the submitted form as well as React state. Browser
    // autofill and session restores fill the visible inputs
    // without firing onChange, which left the state empty and
    // showed a false "enter your email and password" error even
    // though the boxes looked filled in.
    const form = e.currentTarget;
    const formData = form ? new FormData(form) : null;

    const enteredName = String(
      (formData?.get("name") ?? name) || ""
    ).trim();

    const cleanEmail = String(
      (formData?.get("email") ?? email) || ""
    ).trim();

    const enteredPassword = String(
      (formData?.get("password") ?? password) || ""
    );

    const enteredConfirm = String(
      (formData?.get("confirmPassword") ?? confirmPassword) || ""
    );

    if (isRegister && !enteredName) {
      setError("Please enter your name.");
      return;
    }

    if (!cleanEmail || !enteredPassword) {
      setError("Please enter your email and password.");
      return;
    }

    if (isRegister) {
      if (enteredPassword.length < MIN_PASSWORD_LENGTH) {
        setError(
          `Your password must be at least ${MIN_PASSWORD_LENGTH} characters.`
        );
        return;
      }

      if (!enteredConfirm) {
        setError("Please confirm your password.");
        return;
      }

      // Checked here so the mistake is caught before a round trip,
      // and again on the server. The client check is a courtesy,
      // never the guarantee.
      if (enteredConfirm !== enteredPassword) {
        setError("Those two passwords do not match.");
        return;
      }
    }

    setBusy(true);

    try {
      const result = isRegister
        ? await registerUser(
            enteredName,
            cleanEmail,
            enteredPassword
          )
        : await loginUser(cleanEmail, enteredPassword);

      saveUser(result?.user);

      /*
       * Tell the app who is signed in before navigating.
       *
       * The session is checked once when the app loads. Without
       * this the provider still believed nobody was signed in, so
       * RequireAuth bounced straight back to /login and a
       * successful sign-in looked like a failed one.
       */
      await refresh();

      const from = location.state?.from || "/dashboard";

      navigate(from, { replace: true });
    } catch (requestError) {
      setError(
        requestError.message ||
          (isRegister
            ? "Could not create the account. Please try again."
            : "Could not log you in. Please try again.")
      );
    } finally {
      setBusy(false);
    }
  };


  return (
    <div className="login-page">
      {/* Decorative background */}
      <div className="login-background-circle circle-one"></div>
      <div className="login-background-circle circle-two"></div>

      <div className="login-card">
        {/* Logo */}
        <Link to="/home" className="login-logo">
          <div className="logo-icon">R</div>
          <span>
            Resume<span>AI</span>
          </span>
        </Link>

        {/* Heading */}
        <h1>{isRegister ? "Create Account" : "Student Login"}</h1>

        <p className="login-subtitle">
          {isRegister
            ? "Sign up to save your analyses and track your progress"
            : "Sign in to analyze and improve your resume"}
        </p>

        <form onSubmit={handleSubmit}>
          {/* Name - registration only */}
          {isRegister && (
            <div className="input-group">
              <label htmlFor="name">Full Name</label>

              <input
                id="name"
                name="name"
                type="text"
                placeholder="e.g. Vandana Gudihal"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            </div>
          )}

          {/* Email */}
          <div className="input-group">
            <label htmlFor="email">Email Address</label>

            <input
              id="email"
              name="email"
              type="email"
              placeholder="e.g. alex@university.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>

          {/* Password */}
          <div className="input-group">
            <label htmlFor="password">Password</label>

            <div className="password-input-wrapper">
              <input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                placeholder={
                  isRegister
                    ? "At least 8 characters"
                    : "Enter your password"
                }
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={
                  isRegister
                    ? "new-password"
                    : "current-password"
                }
              />
              <button
                type="button"
                className="toggle-password-btn"
                onClick={() => setShowPassword((was) => !was)}
                aria-label={
                  showPassword ? "Hide password" : "Show password"
                }
                // A toggle, so a screen reader is told the state
                // and not only what the button is called.
                aria-pressed={showPassword}
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
          </div>

          {/*
            Confirm password - registration only.

            Shares the one visibility toggle. Revealing one field
            and not the other is the kind of small annoyance that
            makes people mistype a password they just chose.
          */}
          {isRegister && (
            <div className="input-group">
              <label htmlFor="confirmPassword">
                Confirm Password
              </label>

              <div className="password-input-wrapper">
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type={showPassword ? "text" : "password"}
                  placeholder="Type your password again"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                />

                <button
                  type="button"
                  className="toggle-password-btn"
                  onClick={() => setShowPassword((was) => !was)}
                  aria-label={
                    showPassword ? "Hide password" : "Show password"
                  }
                  aria-pressed={showPassword}
                  title={
                    showPassword ? "Hide password" : "Show password"
                  }
                >
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className="login-button"
            disabled={busy}
          >
            {busy
              ? isRegister
                ? "Creating account..."
                : "Signing in..."
              : isRegister
                ? "Create Account"
                : "Sign In"}
          </button>

          {/*
            Sign-in screen: a quiet way across to the existing
            registration view. It is the same component and the same
            route the landing page already uses (`mode: "register"`),
            so there is no second registration page to maintain.

            Shown only on sign-in. The register view keeps its own
            "Already have an account? Sign in" switch below, so the
            two directions stay symmetrical.
          */}
          {!isRegister && (
            <p className="login-register-prompt">
              <span className="login-register-quiet">
                New to ResumeAI?
              </span>{" "}
              <button
                type="button"
                className="login-register-link"
                onClick={() => {
                  setError("");
                  setConfirmPassword("");
                  setMode("register");
                }}
              >
                Create Account
              </button>
            </p>
          )}

          {isRegister && (
            <button
              type="button"
              className="login-switch"
              onClick={() => {
                setError("");
                setConfirmPassword("");
                setMode("login");
              }}
            >
              Already have an account? Sign in
            </button>
          )}

          {/*
            There is deliberately no "Forgot password" link here.

            Nothing on the server can deliver a reset mail - there is
            no SMTP configuration - so a link would either do nothing
            or pretend. It appears only when a real reset flow
            exists: a stored, single-use, expiring token and a
            configured mail sender.
          */}
        </form>

        <p className="login-footer">
          Resume Analysis &amp; Career Intelligence
        </p>
      </div>
    </div>
  );
}

export default Login;
