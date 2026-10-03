from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool

class Write(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=120, description='同一次请求重试使用同号，内容改变须换号')
    expected_version: int = Field(ge=0, strict=True, description='GET /api/workspace 返回的全局 revision')
    actor: str = Field(default='未指定', min_length=1, max_length=80, description='审计标签，不代表认证身份')


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(default='', max_length=160)
    provider: str = Field(default='', max_length=80)


class CreationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identityId: str = Field(min_length=1, max_length=36, description='实际提交的人或AI身份ID；先查询或创建身份')
    initiatedByPersonId: str | None = Field(default=None, max_length=36, description='仅AI代录时指定人类发起者')
    modelInfo: ModelInfo | None = Field(default=None, description='省略则用AI身份默认模型；传空对象明确表示模型未提供')


class IdentityCreate(Write):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal['person', 'agent']
    via: Literal['manual', 'claude_code', 'workbuddy', 'codex', 'deepseek_harness'] = 'manual'
    modelName: str = Field(default='', max_length=160)
    modelProvider: str = Field(default='', max_length=80)


class IdentityUpdate(Write):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    via: Literal['manual', 'claude_code', 'workbuddy', 'codex', 'deepseek_harness'] | None = None
    modelName: str | None = Field(default=None, max_length=160)
    modelProvider: str | None = Field(default=None, max_length=80)


class IssueCreate(Write):
    creation: CreationInput | None = None
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=5000)
    priority: Literal['高', '中', '低'] = '中'
    tag: str = Field(default='', max_length=40)


class IssueUpdate(Write):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    priority: Literal['高', '中', '低'] | None = None
    tag: str | None = Field(default=None, max_length=40)


class IssueTransition(Write):
    action: Literal['triage', 'start', 'verify', 'resolve', 'reject', 'pause', 'resume', 'close-issue', 'reopen', 'retriage']
    reason: str = Field(default='', max_length=5000)
    nextStep: str = Field(default='', max_length=5000)
    successCriteria: str = Field(default='', max_length=5000)
    treatment: str = Field(default='', max_length=5000)
    verificationMethod: str = Field(default='', max_length=5000)
    resolution: str = Field(default='', max_length=5000)
    reviewDate: str = Field(default='', max_length=10)
    closeType: str = Field(default='', max_length=40)
    duplicateOf: str = Field(default='', max_length=120)
    taskPolicy: Literal['', 'detach', 'cancel'] = ''


class Followup(Write):
    content: str = Field(min_length=1, max_length=5000)


class TaskCreate(Write):
    creation: CreationInput | None = None
    title: str = Field(min_length=1, max_length=160)
    issueId: str | None = Field(default=None, max_length=120)
    due: str = Field(default='', max_length=10)
    required: StrictBool = True


class TaskUpdate(Write):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    issueId: str | None = Field(default=None, max_length=120)
    due: str | None = Field(default=None, max_length=10)
    required: StrictBool | None = None


class TaskTransition(Write):
    status: Literal['待办', '进行中', '已完成', '已取消']
    reason: str = Field(default='', max_length=5000)


class Dependencies(Write):
    dependsOn: list[str] = Field(max_length=100)


class Reorder(Write):
    target_id: str = Field(min_length=1, max_length=120)
    after: StrictBool = False
