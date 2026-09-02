#pragma once

#include <QLabel>
#include <QString>
#include <Qt>

class QResizeEvent;
class QWidget;

namespace spellvision::widgets
{

// THE elision helper. One implementation, because there were three and they disagreed.
//
// `applyTelemetryText` in MainWindow.cpp elides with a 6px reserve, ErrorPillLabel elides with a
// 24px reserve plus its prefix, and a third site would have been added here for the video caption
// and the LoRA name. They now all call this: the arithmetic that decides "does this fit" is stated
// once, so a widget that elides cannot elide differently from the widget beside it.
//
// `reserved` is the horizontal space the caller has already spent inside the widget (padding, an
// icon, a prefix). Returns the text unchanged when it fits or when the widget has no width yet --
// eliding against a zero width produces a bare ellipsis, which is how a cold label loses its text.
QString elideForWidget(const QWidget *widget,
                       const QString &text,
                       Qt::TextElideMode mode = Qt::ElideRight,
                       int reserved = 0);

// A QLabel for a value whose LENGTH THE UI DOES NOT CONTROL -- a filename, an absolute path, a
// model name a user chose.
//
// QLabel does not elide: it clips. `setWordWrap(true)` is not a fix, and on 2026-09-02 it was the
// cause of two separate live defects:
//
//   * the video caption wrapped a four-line block (including the full absolute path) under the
//     preview and spent ~64px of a ~330px canvas budget at half height;
//   * the LoRA name was cut mid-glyph at half width, because a name like
//     "Realistic_Anime_Illustrious_v2" has NO break opportunity -- U+005F is not one under
//     UAX-14 -- so wrap had nothing to break, and it also raised the row's minimum width to the
//     widest unbreakable word.
//
// Hence both halves here: the text elides to the width the layout actually gives it, AND the
// widget stops demanding its natural width (`QSizePolicy::Ignored` horizontally, with a small
// floor). Eliding alone would have left the LoRA card still overflowing its scroll viewport.
//
// The full value is always one hover away.
class ElidingLabel final : public QLabel
{
    Q_OBJECT

public:
    explicit ElidingLabel(QWidget *parent = nullptr, Qt::TextElideMode mode = Qt::ElideRight);

    // `toolTip` defaults to the full text; pass a longer block (the caption's detail lines, say)
    // when the tooltip should carry more than the label would have shown.
    void setFullText(const QString &text, const QString &toolTip = QString());
    QString fullText() const { return full_; }
    void clearFullText();

    void setElideMode(Qt::TextElideMode mode);
    Qt::TextElideMode elideMode() const { return mode_; }

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    void refit();

    QString full_;
    Qt::TextElideMode mode_;
};

} // namespace spellvision::widgets
