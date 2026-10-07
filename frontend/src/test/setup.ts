import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// Tam pakette 44 dosya paralel koşar; findBy/waitFor'un 1 s varsayılanı yük
// altında ara ara aşılıyordu (ConvergencePanel vb. kararsız). 3 s yeterli pay.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
});
