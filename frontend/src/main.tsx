import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { App } from "./App";
import { LiveProvider } from "./live";
import { Counter } from "./pages/Counter";
import { Manager } from "./pages/Manager";
import { Analytics } from "./pages/Analytics";
import { StaffView } from "./pages/StaffView";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LiveProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<App />}>
            <Route index element={<Counter />} />
            <Route path="manager" element={<Manager />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="staff/:id?" element={<StaffView />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </LiveProvider>
  </StrictMode>,
);
