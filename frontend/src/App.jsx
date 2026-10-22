import { useEffect } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  useNavigate,
} from "react-router-dom";

import Home from "./pages/Home";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import CareerProfile from "./pages/CareerProfile";
import CareerMission from "./pages/CareerMission";
import JobMatch from "./pages/JobMatch";
import InterviewPrep from "./pages/InterviewPrep";
import TemplateGallery from "./pages/TemplateGallery";
import ResumeBuilder from "./pages/ResumeBuilder";
import MyResumes from "./pages/MyResumes";
import FindJobs from "./pages/FindJobs";
// removed InterviewPrep and SkillPassport imports
import Applications from "./pages/Applications";
import AnalyseResume from "./pages/AnalyseResume";
import CreateResume from "./pages/CreateResume";
import MyDetails from "./pages/MyDetails";
import CoverLetter from "./pages/CoverLetter";
// removed InterviewPrep import
import { onAuthFailure } from "./services/api";
import { clearAuthState } from "./services/authSession";
import { SessionProvider } from "./services/sessionContext";
import { useSession as useSessionContext } from "./services/sessionStore";

/**
 * Asks the backend who the current session belongs to.
 *
 * This used to be a plain hook that each caller ran for itself,
 * which meant opening the root URL fired three parallel `/auth/me`
 * requests and spent most of a second on "Checking your session..."
 * before it could decide. It is a provider now - see
 * sessionContext.jsx - and the check runs once per page load.
 */
function useSession() {
  return useSessionContext();
}

/** Shown while the session is being checked. */
function CheckingSession() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "14px",
        fontFamily: "Inter, -apple-system, sans-serif",
        color: "#788194",
        background: "#f8faff",
      }}
    >
      <div
        className="spinner"
        style={{
          width: "30px",
          height: "30px",
          border: "3px solid #e5e7ee",
          borderTopColor: "#3155d9",
          borderRadius: "50%",
          animation: "spin 0.8s linear infinite",
        }}
      />
      <p style={{ margin: 0, fontSize: "15px" }}>
        Checking your session...
      </p>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

/**
 * Sends the user to Login the moment the server reports the session
 * is gone.
 *
 * RequireAuth only checks once, when a page mounts. Without this,
 * a session that expires while somebody is already on a page left
 * them sitting on a protected screen that could no longer load
 * anything, and nothing told them why.
 *
 * Lives inside the Router so it can use the navigator.
 */
function AuthFailureWatcher() {
  const navigate = useNavigate();

  useEffect(() => {
    return onAuthFailure(() => {
      // Drop cached state before navigating, so nothing private is
      // rendered on the way out.
      clearAuthState();

      // replace, so the protected page is not left in history for
      // the Back button to return to.
      navigate("/login", { replace: true });
    });
  }, [navigate]);

  return null;
}

/**
 * Blocks a page until we know whether a session exists.
 */
function RequireAuth({ children }) {
  const location = useLocation();
  const { loading, user } = useSession();

  if (loading) {
    return <CheckingSession />;
  }

  if (!user) {
    // Remember where they were heading so login can return them.
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  return children;
}

/**
 * The root URL is the front door for the session:
 *   signed in  -> straight to the dashboard
 *   signed out -> straight to Student Login
 *
 * The Home page is untouched and still lives at /home.
 */
function RootRedirect() {
  const { loading, user } = useSession();

  if (loading) {
    return <CheckingSession />;
  }

  return (
    <Navigate to={user ? "/dashboard" : "/login"} replace />
  );
}

/**
 * The public landing page.
 *
 * Public for a signed-out visitor. For somebody who is already
 * signed in it is the wrong page: the logo, the "Home" link and
 * "Back to Home" all land here, and a signed-in user has an app to
 * go to. So the session decides which of the two they get.
 */
function LandingPage() {
  const { loading, user } = useSession();

  if (loading) {
    return <CheckingSession />;
  }

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Home />;
}

function App() {
  return (
    <BrowserRouter>
      {/* One session for the whole app, and the inactivity clock
          that ends it. */}
      <SessionProvider>
        {/* Mounted once, ahead of the guarded pages. */}
        <AuthFailureWatcher />

      <Routes>
        {/* Root now leads to Login, or the Dashboard when signed in */}
        <Route path="/" element={<RootRedirect />} />

        {/* Student Login / Register */}
        <Route path="/login" element={<Login />} />

        {/* ResumeAI Dashboard - login required */}
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />

        {/* Career Profile - login required */}
        <Route
          path="/career-profile"
          element={
            <RequireAuth>
              <CareerProfile />
            </RequireAuth>
          }
        />

        {/* Career Mission - login required */}
        <Route
          path="/career-mission"
          element={
            <RequireAuth>
              <CareerMission />
            </RequireAuth>
          }
        />

        {/* Evidence-based job match - login required */}
        <Route
          path="/job-match"
          element={
            <RequireAuth>
              <JobMatch />
            </RequireAuth>
          }
        />

        {/* Readiness practice - login required.

            The practice page was kept in the project when its card was
            removed. Job match now links to it for the practical part
            of an action plan: answering questions and keeping the
            feedback, separate from the resume score. */}
        <Route
          path="/interview-practice"
          element={
            <RequireAuth>
              <InterviewPrep />
            </RequireAuth>
          }
        />

        {/* Find Jobs - login required */}
        <Route
          path="/find-jobs"
          element={
            <RequireAuth>
              <FindJobs />
            </RequireAuth>
          }
        />

        {/* Saved Jobs - the same page, opened on the saved list */}
        <Route
          path="/saved-jobs"
          element={
            <RequireAuth>
              <FindJobs initialTab="saved" />
            </RequireAuth>
          }
        />

        {/* Application Tracker - login required */}
        <Route
          path="/applications"
          element={
            <RequireAuth>
              <Applications />
            </RequireAuth>
          }
        />

        {/* Analyse My Resume - its own page, login required.

            This was a section of the dashboard. The card's click
            scrolled to one panel buried below the launcher and the
            feature grid, which is why the button read as broken:
            it navigated, but it arrived nowhere useful. */}
        <Route
          path="/analyse"
          element={
            <RequireAuth>
              <AnalyseResume />
            </RequireAuth>
          }
        />

        {/* Create My Resume opens the Resume Studio: the template gallery
            first.

            It used to open the details form, on the reasoning that
            writing the details should come before choosing a design.
            That is no longer the arrangement: My Profile is now its
            own page, reached from the dashboard, and holding the
            master record is a separate decision from making a resume.

            So this route is the gallery. It is deliberately NOT behind
            the auth guard - a visitor with no account, or an account
            with an empty profile, must still be able to browse and
            compare designs. Nothing here needs an account; only
            saving does.

            /my-details below still exists as the profile editor for
            the profile-first journey, and the gallery links to it
            rather than redirecting into it. */}
        <Route path="/create-resume" element={<TemplateGallery />} />

        {/* The same page under a name that says what it is. Both paths
            exist because /create-resume is linked from the dashboard
            and from My Resumes, and repointing that link would have
            broken the bookmarks people already have. */}
        <Route
          path="/my-details"
          element={
            <RequireAuth>
              <MyDetails />
            </RequireAuth>
          }
        />

        {/* Cover letters - their own documents, separate from resumes.

            Behind the auth guard: a letter is private to the account
            that wrote it, and there is nothing here an anonymous
            visitor could do.

            The `:letterId` form opens one letter directly, so a
            bookmark or a shared link lands on that document rather
            than on the library with the user hunting for it. */}
        <Route
          path="/cover-letter"
          element={
            <RequireAuth>
              <CoverLetter />
            </RequireAuth>
          }
        />

        <Route
          path="/cover-letter/:letterId"
          element={
            <RequireAuth>
              <CoverLetter />
            </RequireAuth>
          }
        />

        {/* Skill Passport has no route.

            It was removed from the primary interface, not from the
            project: SkillPassport.jsx, its CSS and the backend
            endpoints are still here and still tested. Nothing in the
            sidebar or on the dashboard links to it. It is not deleted
            because deleting working code is not what removing a card
            means - if it is ever wanted back, the route is one line
            and the feature underneath it is untouched.

            Interview practice is back under /interview-practice,
            linked from Job match, because readiness practice is part
            of the action-plan workflow rather than a dashboard card. */}

        {/* Kept, not deleted.

            The original details form that wrote a resume document
            directly. Nothing links here any more - My Resumes has its
            own blank-start button and the gallery has its own
            template-start - but removing a working page is not this
            task's call. It is preserved until it is either used or
            explicitly retired. */}
        <Route
          path="/create-resume/from-details"
          element={
            <RequireAuth>
              <CreateResume />
            </RequireAuth>
          }
        />

        {/* Resume Studio: browse templates without an account.

            Both template entry points render the same page, which
            picks its heading and its Resume/CV selection from the
            route. There is no CV-only design in the registry - every
            layout is a general document layout - so the two routes
            are two names for one real catalogue, not two lists. They
            stay separate so either can be bookmarked. */}
        <Route
          path="/resume-templates"
          element={<TemplateGallery />}
        />

        <Route
          path="/cv-templates"
          element={<TemplateGallery />}
        />

        {/* Saved resumes and the editor - login required */}
        <Route
          path="/my-resumes"
          element={
            <RequireAuth>
              <MyResumes />
            </RequireAuth>
          }
        />

        <Route
          path="/resume-builder/:resumeId"
          element={
            <RequireAuth>
              <ResumeBuilder />
            </RequireAuth>
          }
        />

        {/* Home is the public landing page. It is for people who are
            not signed in.

            Someone who already has a session has no business being
            shown the marketing page: the logo in the sidebar and the
            "Home" link used to drop them here, where every call to
            action pointed back at the app. They go to their dashboard
            instead, which is the page they actually came for. */}
        <Route path="/home" element={<LandingPage />} />

        {/* Fallback */}
        <Route
          path="*"
          element={<Navigate to="/" replace />}
        />
      </Routes>
      </SessionProvider>
    </BrowserRouter>
  );
}

export default App;
