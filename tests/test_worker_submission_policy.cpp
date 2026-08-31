#include "workers/WorkerSubmissionPolicy.h"

#include <QJsonObject>
#include <QString>
#include <iostream>

using spellvision::workers::WorkerSubmissionPolicy;

static int g_failed = 0;

static void expect_true(bool cond, const char *name)
{
    if (!cond)
    {
        std::cerr << "FAIL " << name << "\n";
        ++g_failed;
    }
}

static void expect_false(bool cond, const char *name)
{
    expect_true(!cond, name);
}

static void expect_contains(const QString &haystack, const QString &needle, const char *name)
{
    if (!haystack.contains(needle))
    {
        std::cerr << "FAIL " << name << " got " << haystack.toStdString() << "\n";
        ++g_failed;
    }
}

static void expect_not_contains(const QString &haystack, const QString &needle, const char *name)
{
    if (haystack.contains(needle))
    {
        std::cerr << "FAIL " << name << " got " << haystack.toStdString() << "\n";
        ++g_failed;
    }
}

int main()
{
    {
        QJsonObject payload;
        expect_false(WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload),
                     "empty payload is not a native stack");
    }

    {
        QJsonObject stack;
        stack.insert(QStringLiteral("stack_kind"), QStringLiteral("wan_dual_noise"));
        QJsonObject payload;
        payload.insert(QStringLiteral("video_model_stack"), stack);
        expect_false(WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload),
                     "non-empty stack with empty paths is not a native stack");
    }

    {
        QJsonObject payload;
        payload.insert(QStringLiteral("native_video_stack_kind"), QStringLiteral("wan_dual_noise"));
        expect_false(WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload),
                     "kind-only is not a native stack");
    }

    {
        QJsonObject stack;
        stack.insert(QStringLiteral("primary_path"), QStringLiteral("D:/models/hunyuan.safetensors"));
        QJsonObject payload;
        payload.insert(QStringLiteral("video_model_stack"), stack);
        expect_true(WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload),
                    "primary_path is a real native stack");
    }

    {
        QJsonObject stack;
        stack.insert(QStringLiteral("high_noise_path"), QStringLiteral("D:/models/wan_high.safetensors"));
        stack.insert(QStringLiteral("low_noise_path"), QStringLiteral("D:/models/wan_low.safetensors"));
        QJsonObject payload;
        payload.insert(QStringLiteral("model_stack"), stack);
        expect_true(WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload),
                    "high+low paths are a real native stack");
    }

    {
        QJsonObject stack;
        stack.insert(QStringLiteral("high_noise_path"), QStringLiteral("D:/models/wan_high.safetensors"));
        QJsonObject payload;
        payload.insert(QStringLiteral("video_model_stack"), stack);
        expect_false(WorkerSubmissionPolicy::hasNativeVideoStackPayload(payload),
                     "high without low is not a native stack");
    }

    {
        const QString line = WorkerSubmissionPolicy::acceptedRequestLogLine(
            QStringLiteral("t2v"), true, false, QStringLiteral("ltx-2.3-distilled.safetensors"));
        expect_contains(line, QStringLiteral("native video"), "ltx filename is native video not Prompt API");
        expect_not_contains(line, QStringLiteral("Prompt API"), "ltx filename heuristic removed");
    }

    {
        const QString line = WorkerSubmissionPolicy::acceptedRequestLogLine(
            QStringLiteral("t2v"), true, true, QStringLiteral("ltx-2.3-distilled.safetensors"));
        expect_contains(line, QStringLiteral("workflow video"), "workflow binding stays workflow video");
    }

    if (g_failed != 0)
    {
        std::cerr << g_failed << " assertion(s) failed\n";
        return 1;
    }
    std::cout << "ok\n";
    return 0;
}
