// ARKA 3.0 - arka-bot
// FICTIONAL FOR TRAINING USE ONLY - PROTOTYP SZKOLENIOWY
// Nie produkcja. Nie prawdziwa weryfikacja.

import express from "express";
import cors from "cors";
import helmet from "helmet";

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json({ limit: "1mb" }));

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    project: "arka-bot",
    mode: "FICTIONAL FOR TRAINING USE ONLY",
    version: "0.1.0-prototype"
  });
});

app.get("/", (req, res) => {
  res.json({
    message: "ARKA 3.0 prototype - szkoleniowy",
    endpoints: ["/health", "/api/verify (mock)"]
  });
});

// MOCK - nie prawdziwa weryfikacja ZK, tylko placeholder do testów UI
app.post("/api/verify", (req, res) => {
  res.json({
    verified: false,
    reason: "MOCK - prototyp, brak prawdziwego vkey.json",
    received: req.body || {}
  });
});

app.listen(PORT, () => {
  console.log(`ARKA prototype listening on ${PORT}`);
});
