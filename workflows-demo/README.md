# Hello World - Render Workflows (TypeScript)

This hello-world example demonstrates three foundational workflow patterns:

- A minimal task definition (`calculateSquare`)
- A task that chains runs of another task (`sumSquares`)
- A task with custom retry behavior (`flipCoin`)

## What You'll Learn

- How to define tasks with `task(...)`
- How to chain task runs using `await` and `Promise.all`
- How to customize retry behavior with `retry`

## Example Tasks

### `calculateSquare(a: number): number`

The smallest possible task: takes one number and returns its square.

### `sumSquares(a: number, b: number): Promise<number>`

Chains two runs of `calculateSquare` and sums the results.

It uses `Promise.all(...)` to chain the two runs in parallel:

```ts
const [result1, result2] = await Promise.all([
  calculateSquare(a),
  calculateSquare(b),
]);
```

### `flipCoin(): string`

Simulates a coin flip:

- Heads: Returns success
- Tails: Raises an error to trigger retry

Retry policy in this example:

- max retries: `3`
- wait duration: `1000ms`
- backoff scaling: `1.5`

## Local Development

### Prerequisites

- Node.js 18+

### Run locally

> Make sure you've installed the latest version of the [Render CLI](https://render.com/docs/cli).

1. From this template's root, start the local task server:

    ```bash
    npm install
    render workflows dev -- npm start
    ```

2. In a separate terminal, trigger task runs:

    ```bash
    render workflows tasks start calculateSquare --local --input='[5]'
    render workflows tasks start sumSquares --local --input='[3,4]'
    render workflows tasks start flipCoin --local --input='[]'
    ```

Expected behavior:

- `calculateSquare` with `5` returns `25`
- `sumSquares` with `3,4` returns `25`
- `flipCoin` may fail and retry before succeeding

## Deploying to Render

Configure your Workflow service with:

| Option | Value |
| --- | --- |
| Build command | `npm install` |
| Start command | `npm start` |

## Key Concepts

### Task registration

Any call to `task({ name: ... }, handler)` registers a runnable workflow task.

### Chaining runs

Inside an async task, calling `await anotherTask(...)` chains a run of that task.

### Retries

Use the `retry` option in task config when transient failures should be retried automatically.

## Troubleshooting

### "Task not found"

- Confirm the service is running
- Verify task names exactly match: `calculateSquare`, `sumSquares`, `flipCoin`

### Import or dependency issues

- Confirm dependency install completed from `package.json`
- Confirm Node.js version is 18+

## Resources

- [Render Workflows documentation](https://render.com/docs/workflows)
- [Workflows tutorial](https://render.com/docs/workflows-tutorial)
- [Local development guide](https://render.com/docs/workflows-local-development)
