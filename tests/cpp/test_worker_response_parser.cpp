// The UI's half of the "unregistered message type" bug.
//
// A worker message type registered in neither worker_client nor here was discarded TWICE: the
// Python client wrapped it in a `client_warning` envelope whose own `ok` was true, and this parser
// then had no case for `client_warning` at all, so it fell through to MessageKind::Unknown and
// applyOk read the envelope's true.
//
// The sharpest instance was `auth_error`, emitted by the authorisation gate on every command: an
// authorisation REFUSAL reached the UI as a success.
//
// This is the first C++ test of decision logic in the repo, which is the gap Doc 50's own ratchet
// table names: "every ratchet here is Python. The C++ side has no equivalent, and two defects in
// this pass lived there."

#include <QtTest>

#include "workers/WorkerResponseParser.h"

using spellvision::workers::WorkerResponseParser;
using MessageKind = WorkerResponseParser::MessageKind;
using JobState = WorkerResponseParser::JobState;

class WorkerResponseParserTest : public QObject
{
    Q_OBJECT

private slots:
    void aWrappedMessageIsRecognised();
    void aWrappedMessageIsNotReportedAsSuccess();
    void aWrappedMessageAlwaysCarriesAnExplanation();
    void aWrappedMessageKeepsThePayload();
    void anUnknownKindIsStillUnknown();
    void everyKindRoundTripsThroughItsName_data();
    void everyKindRoundTripsThroughItsName();
    void terminalStatesAreClassifiedConsistently_data();
    void terminalStatesAreClassifiedConsistently();
};

void WorkerResponseParserTest::aWrappedMessageIsRecognised()
{
    QJsonObject payload{
        {QStringLiteral("type"), QStringLiteral("client_warning")},
        {QStringLiteral("ok"), false},
        {QStringLiteral("warning"), QStringLiteral("Unknown worker message type: 'auth_error'")},
    };
    const auto parsed = WorkerResponseParser::parseObject(payload);
    QCOMPARE(parsed.kind, MessageKind::ClientWarning);
}

void WorkerResponseParserTest::aWrappedMessageIsNotReportedAsSuccess()
{
    // Both halves of the fix have to hold for this. The envelope's `ok` now comes from
    // worker_client, which sets it FALSE for an unrecognised type -- so strictly this assertion is
    // carried by the Python side today. It lives here as the cross-language guarantee: if either
    // side regresses, an authorisation refusal reaches the UI as a success again, and this is the
    // test that says so from the UI's point of view.
    QJsonObject inner{
        {QStringLiteral("type"), QStringLiteral("auth_error")},
        {QStringLiteral("ok"), false},
        {QStringLiteral("error"), QStringLiteral("not authorised")},
    };
    QJsonObject payload{
        {QStringLiteral("type"), QStringLiteral("client_warning")},
        {QStringLiteral("ok"), false},
        {QStringLiteral("warning"), QStringLiteral("Unknown worker message type: 'auth_error'")},
        {QStringLiteral("raw"), inner},
    };

    const auto parsed = WorkerResponseParser::parseObject(payload);
    QVERIFY(parsed.hasOk);
    QVERIFY2(!parsed.ok, "an authorisation refusal must not reach the UI as a success");
}

void WorkerResponseParserTest::aWrappedMessageAlwaysCarriesAnExplanation()
{
    // Even with nothing useful inside it. A wrapped message means this build does not understand
    // something the worker sent -- a version skew, or a type registered on neither side -- and the
    // previous behaviour was a silent no-op.
    QJsonObject bare{
        {QStringLiteral("type"), QStringLiteral("client_warning")},
        {QStringLiteral("ok"), false},
    };
    const auto parsed = WorkerResponseParser::parseObject(bare);
    QVERIFY2(!parsed.errorText.isEmpty(),
             "a message the UI cannot interpret must say so rather than vanishing");
}

void WorkerResponseParserTest::aWrappedMessageKeepsThePayload()
{
    QJsonObject inner{
        {QStringLiteral("type"), QStringLiteral("model_import_result")},
        {QStringLiteral("ok"), true},
        {QStringLiteral("filename"), QStringLiteral("model.safetensors")},
    };
    QJsonObject payload{
        {QStringLiteral("type"), QStringLiteral("client_warning")},
        {QStringLiteral("ok"), false},
        {QStringLiteral("raw"), inner},
    };

    const auto parsed = WorkerResponseParser::parseObject(payload);
    QCOMPARE(parsed.raw.value(QStringLiteral("raw")).toObject()
                 .value(QStringLiteral("filename")).toString(),
             QStringLiteral("model.safetensors"));
}

void WorkerResponseParserTest::anUnknownKindIsStillUnknown()
{
    // client_warning must not become a catch-all: a genuinely unrecognised type still reports
    // Unknown, so the two cases stay distinguishable.
    const auto parsed = WorkerResponseParser::parseObject({
        {QStringLiteral("type"), QStringLiteral("something_nobody_registered")},
    });
    QCOMPARE(parsed.kind, MessageKind::Unknown);
}

void WorkerResponseParserTest::everyKindRoundTripsThroughItsName_data()
{
    QTest::addColumn<int>("kind");
    // Every enumerator, so adding one without teaching kindFromString/kindName about it fails here
    // rather than in the field. Unknown is excluded: it is the fallback, not a wire name.
    const MessageKind kinds[] = {
        MessageKind::Status, MessageKind::Progress, MessageKind::Result, MessageKind::Error,
        MessageKind::JobUpdate, MessageKind::QueueSnapshot, MessageKind::QueueAck,
        MessageKind::RuntimeStatus, MessageKind::RuntimeAck, MessageKind::WorkflowImportResult,
        MessageKind::WorkflowProfiles, MessageKind::LtxUiQueueHistoryContract,
        MessageKind::ClientError, MessageKind::ClientWarning,
    };
    for (MessageKind kind : kinds)
        QTest::newRow(qPrintable(WorkerResponseParser::kindName(kind))) << int(kind);
}

void WorkerResponseParserTest::everyKindRoundTripsThroughItsName()
{
    QFETCH(int, kind);
    const auto original = MessageKind(kind);
    const QString name = WorkerResponseParser::kindName(original);
    QVERIFY2(!name.isEmpty(), "every kind needs a wire name");
    QCOMPARE(WorkerResponseParser::kindFromString(name), original);
}

void WorkerResponseParserTest::terminalStatesAreClassifiedConsistently_data()
{
    QTest::addColumn<QString>("state");
    QTest::addColumn<bool>("terminal");
    QTest::addColumn<bool>("successful");

    QTest::newRow("queued") << "queued" << false << false;
    QTest::newRow("starting") << "starting" << false << false;
    QTest::newRow("running") << "running" << false << false;
    QTest::newRow("completed") << "completed" << true << true;
    QTest::newRow("failed") << "failed" << true << false;
    QTest::newRow("cancelled") << "cancelled" << true << false;
}

void WorkerResponseParserTest::terminalStatesAreClassifiedConsistently()
{
    QFETCH(QString, state);
    QFETCH(bool, terminal);
    QFETCH(bool, successful);

    const JobState parsed = WorkerResponseParser::stateFromString(state);
    QCOMPARE(WorkerResponseParser::isTerminalState(parsed), terminal);
    QCOMPARE(WorkerResponseParser::isSuccessfulTerminal(parsed), successful);
    // A state cannot be both a success and a failure, and a non-terminal state is neither.
    QVERIFY(!(WorkerResponseParser::isSuccessfulTerminal(parsed)
              && WorkerResponseParser::isFailedTerminal(parsed)));
    if (!terminal)
        QVERIFY(!WorkerResponseParser::isFailedTerminal(parsed));
}

QTEST_MAIN(WorkerResponseParserTest)
#include "test_worker_response_parser.moc"
