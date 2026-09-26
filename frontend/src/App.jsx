import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import Home from "./pages/Home";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Landing / Home Page */}
        <Route path="/" element={<Home />} />

        {/* Student Login */}
        <Route path="/login" element={<Login />} />

        {/* ResumeAI Dashboard */}
        <Route path="/dashboard" element={<Dashboard />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;