#include "HomeModuleBase.h"

HomeModuleBase::HomeModuleBase(QWidget *parent)
    : QWidget(parent)
{
}

void HomeModuleBase::setRuntimeSummary(const HomeRuntimeSummary &summary)
{
    runtimeSummary_ = summary;
}

void HomeModuleBase::setCustomizeMode(bool enabled)
{
    customizeMode_ = enabled;
}
