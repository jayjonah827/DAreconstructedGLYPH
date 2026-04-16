import { task } from "@renderinc/sdk/workflows"

const calculateSquare = task(
  { name: "calculateSquare" },
  async (n: number) => n * n
);

const processClaim = task(
  {
    name: "processClaim",
    retry: { maxRetries: 3, waitDurationMs: 1000, backoffScaling: 1.5 },
    timeoutSeconds: 300,
    plan: "standard",
  },
  async (claim: { id: string; value: number }) => {
    const result = await calculateSquare(claim.value);
    return { claimId: claim.id, result };
  }
);
