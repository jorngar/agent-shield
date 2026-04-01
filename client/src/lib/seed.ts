/**
 * Run once to seed Firestore with demo intercepts.
 * Usage: call seedFirestore() from browser console or a dev button.
 *
 * import { seedFirestore } from "@/lib/seed";
 * seedFirestore().then(() => console.log("done"));
 */

import {
  collection,
  doc,
  setDoc,
  getDocs,
  Timestamp,
} from "firebase/firestore";
import { db } from "./firebase";
import { mockIntercepts } from "./mock-data";

export async function seedFirestore(): Promise<void> {
  const col = collection(db, "intercepts");
  const existing = await getDocs(col);

  if (!existing.empty) {
    console.info(`[seed] Firestore already has ${existing.size} intercepts — skipping.`);
    return;
  }

  console.info("[seed] Seeding Firestore with demo intercepts…");

  for (const intercept of mockIntercepts) {
    const { id, timestamp, decidedAt, ...rest } = intercept;
    await setDoc(doc(col, id), {
      ...rest,
      timestamp: Timestamp.fromDate(new Date(timestamp)),
      ...(decidedAt ? { decidedAt: Timestamp.fromDate(new Date(decidedAt)) } : {}),
    });
    console.info(`[seed] ✓ ${id} — ${intercept.toolName}`);
  }

  console.info("[seed] Done. Refresh the dashboard.");
}

export async function clearFirestore(): Promise<void> {
  const col = collection(db, "intercepts");
  const snap = await getDocs(col);
  for (const d of snap.docs) {
    await setDoc(doc(col, d.id), { _deleted: true }); // soft clear
  }
  console.info("[seed] Cleared.");
}
