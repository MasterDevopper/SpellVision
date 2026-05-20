#pragma once

// SpellVision — Chain Studio headless self-test (Pass 6).
//
// The verification checkpoint. Builds real ChainStore + real
// ChainCompletionWatcher + real ChainEngine wired to a real
// QueueManager, fakes only the submission callback. Runs scripted
// scenarios that drive the full engine state machine and asserts the
// observable outcomes (status transitions, variation finalization,
// cascade behavior, persistence round-trip).
//
// Invocation:
//   SpellVision.exe --chain-selftest
//
// Exit codes:
//   0      all scenarios passed
//   1..N   N scenarios failed (also printed to stdout)
//
// This is a one-shot harness: returns from main without ever
// constructing MainWindow. Safe to wire into the production binary
// because the flag check happens BEFORE any UI setup.

namespace spellvision::chain
{

// Returns the number of failed scenarios. 0 means everything passed.
// Prints PASS/FAIL lines to stdout per scenario.
int runChainSelfTest();

} // namespace spellvision::chain
