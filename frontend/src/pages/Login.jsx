import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import "./Login.css";

function Login() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = (e) => {
    e.preventDefault();

    if (!email.trim() || !password.trim()) {
      setError("Please enter your email and password.");
      return;
    }

    setError("");

    // Generate nice display name from email (e.g. "alex.smith@gmail.com" -> "Alex Smith")
    const username = email.split("@")[0] || "User";
    const displayName = username
      .replace(/[._-]/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());

    // Save profile to localStorage for personalizing Dashboard
    try {
      localStorage.setItem(
        "resumeai_user",
        JSON.stringify({
          email: email.trim(),
          name: displayName,
          loggedInAt: new Date().toISOString(),
        })
      );
    } catch (err) {
      console.warn("Could not save user to localStorage", err);
    }

    // After successful login → ResumeAI dashboard
    navigate("/dashboard");
  };

  const handleDemoLogin = () => {
    try {
      localStorage.setItem(
        "resumeai_user",
        JSON.stringify({
          email: "student.demo@resumeai.dev",
          name: "Vandana",
          loggedInAt: new Date().toISOString(),
        })
      );
    } catch (err) {
      console.warn(err);
    }
    navigate("/dashboard");
  };

  return (
    <div className="login-page">
      {/* Decorative background */}
      <div className="login-background-circle circle-one"></div>
      <div className="login-background-circle circle-two"></div>

      <div className="login-card">
        {/* Back Link */}
        <Link to="/" className="back-home-link">
          ← Back to Home
        </Link>

        {/* Logo */}
        <Link to="/" className="login-logo">
          <div className="logo-icon">R</div>
          <span>
            Resume<span>AI</span>
          </span>
        </Link>

        {/* Heading */}
        <h1>Student Login</h1>

        <p className="login-subtitle">
          Sign in to analyze and improve your resume
        </p>

        <form onSubmit={handleLogin}>
          {/* Email */}
          <div className="input-group">
            <label htmlFor="email">Email Address</label>

            <input
              id="email"
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
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
              <button
                type="button"
                className="toggle-password-btn"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "👁️" : "👁️‍🗨️"}
              </button>
            </div>
          </div>

          {/* Error */}
          {error && <div className="login-error">{error}</div>}

          {/* Login button */}
          <button type="submit" className="login-button">
            Login to Dashboard
          </button>

          {/* Quick Demo Login */}
          <button
            type="button"
            className="demo-login-button"
            onClick={handleDemoLogin}
          >
            ⚡ Quick Demo Sign-in (1-Click)
          </button>
        </form>

        <p className="login-footer">
          AI-Powered Resume Analysis & Career Intelligence
        </p>
      </div>
    </div>
  );
}

export default Login;