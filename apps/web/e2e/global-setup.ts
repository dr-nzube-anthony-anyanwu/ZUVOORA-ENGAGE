import { createFixtures, removeFixtures } from "./fixtures";

/** Create synthetic users/clinics for the run; the returned function removes them afterwards. */
export default async function globalSetup() {
  const fixtures = await createFixtures();
  process.env.E2E_FIXTURES = JSON.stringify(fixtures);
  return async () => {
    await removeFixtures(fixtures);
  };
}
