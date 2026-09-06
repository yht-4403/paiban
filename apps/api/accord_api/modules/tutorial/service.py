"""Idempotent reference material and an explicit virtual exploration example."""

import hashlib
from dataclasses import dataclass

from accord_api.modules.identity import service as identity
from accord_api.modules.knowledge import index
from accord_api.modules.knowledge.resources import create_resource
from accord_api.modules.tutorial import exploration_fixture
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


@dataclass(frozen=True)
class TutorialResource:
    id: str
    owner_id: str
    owner_name: str
    title: str
    focus: str
    body: str


TUTORIAL_RESOURCES = (
    TutorialResource(
        id='tutorial_context_fixed_trial_1_v1',
        owner_id='fixed_trial_1',
        owner_name='体验者一',
        title='体验者一-拍办路演统筹与工程进展.md',
        focus='项目统筹与工程进展',
        body="""# 拍办路演统筹与工程进展

## 我的职责

我是体验者一，负责本次拍办路演的项目统筹、现场联调和最终串场。路演计划在明天上午进行，现场用三个浏览器窗口分别登录三位体验成员，所有问答、会议和任务都由演示者真实操作。

## 当前目标

- 用一条连续流程讲清楚「先问同事 Agent，再由人拍板」。
- 展示 Agent 只读取成员主动共享的工作池资料，并能给出可展开的来源。
- 会前先收集三人的上下文，再决定参会者和任务负责人。
- 任务先由负责人在自己的工作台对话里完成；本人勾选后，系统直接读取这段对话、生成总结并沉淀记忆。

## 当前依赖

- 体验者二负责产品定位、路演叙事和关键取舍，适合回答「为什么要做拍办」以及决定路演主线。
- 体验者三负责前端体验和 1440 像素桌面宽度复核，适合承接界面验收任务。
- 我负责把产品结论、UI 验收和工程流程串成现场操作顺序。

## 待确认事项

1. 路演开场是否只保留「问 Agent、开决策会、分配任务」三段。
2. 1440 像素下右侧资料区、聊天区和待办入口是否都能被评委看清。
3. 演示结束前是否能在体验者三的工作台对话中完成 UI 复核，再由待办整理流程直接读取结果。

## 协作约定

准备资料不代表任务已经创建或完成。会议名单、任务负责人和完成状态必须由现场用户在拍办中确认。若需要产品方向拍板，应邀请体验者二；若只是执行 1440 像素 UI 复核，可以直接推荐体验者三负责。
""",
    ),
    TutorialResource(
        id='tutorial_context_fixed_trial_2_v1',
        owner_id='fixed_trial_2',
        owner_name='体验者二',
        title='体验者二-产品定位与路演决策.md',
        focus='产品与路演决策',
        body="""# 拍办产品定位与路演决策

## 我的职责

我是体验者二，负责拍办的产品定位、路演主线和关键范围取舍。遇到「讲什么、砍什么、为什么这样设计」的问题，需要由我提供上下文并作最终判断。

## 已采用的产品主线

拍办面向已经大量使用 AI 的小团队。每位成员有一个专属 Agent；同事先向 Agent 提问，Agent 只依据该成员授权共享的资料回答。答案不能解决问题时，用户再在原对话中找本人。核心价值是减少重复解释，同时把决策、承诺和任务放行留给人。

## 明日路演取舍

- 主演示聚焦三个动作：找同事 Agent、发起决策会、分配并完成任务。
- 不播放预录流程，不预制模型答案，不伪造会议或任务完成状态。
- 工作池只放成员愿意让团队与其 Agent 读取的成品；临时附件不自动公开。
- Agent 回答必须显示资料来源。没有依据时应直接说明资料不足。
- 找本人保持在同一个对话里，不新增倒计时弹窗。

## 决策会建议

如果议题是「确定明天的路演主线」，我属于关键决策人，应参加。体验者一负责统筹，也应参加。体验者三已经通过共享资料提供 UI 执行信息时，不必为了重复同步而参会；若议题包含尚未明确的界面取舍，再邀请体验者三。

## 可交付内容

我适合负责 90 秒产品开场稿、价值主张和演示范围拍板。目前可以提供明确方向，但正式任务仍需发起人在拍办中选择负责人后才成立。
""",
    ),
    TutorialResource(
        id='tutorial_context_fixed_trial_3_v1',
        owner_id='fixed_trial_3',
        owner_name='体验者三',
        title='体验者三-工作台UI与1440宽度复核.md',
        focus='UI 与 1440 宽度复核',
        body="""# 拍办工作台 UI 与 1440 宽度复核

## 我的职责

我是体验者三，负责拍办的前端体验、视觉层级和 1440 像素桌面宽度验收。界面复核、文案精简、资料区布局和新手路径检查应优先由我承接。

## 本轮复核范围

- 左侧只保留身份、聊天入口和必要导航，搜索位置稳定。
- 中间聊天区是主要视觉区域，Agent、本人和系统状态能够一眼区分。
- 右侧资料区默认紧凑，可展开来源，不堆放解释性小字。
- 待办作为贯穿流程的状态出现，不作为独立的大功能入口。
- 输入框、主按钮和当前下一步在 1440 像素宽度下无需横向滚动即可看到。
- 找本人沿用原对话，不使用倒计时弹窗。

## 验收方法

使用 1440 × 900 浏览器视口依次检查个人工作台、同事 Agent 对话、会议信息收集和任务详情。重点记录遮挡、内容跳动、按钮不可见、文字过小以及视觉权重错误，并给出「通过 / 需修改」结论和可复查截图说明。

## 当前判断

如果任务是「复核 1440 像素下工作台布局并提交结论」，我的职责和既往上下文匹配度最高，可以被推荐为负责人。该说明只是推荐依据；必须由发起人亲自选择后才形成待办，完成时还需先在本人的工作台对话里产出真实复核结果，再勾选确认。
""",
    ),
)

TUTORIAL_RESOURCE_BY_ID = {item.id: item for item in TUTORIAL_RESOURCES}
TRIAL_ACCOUNT_IDS = frozenset(item.owner_id for item in TUTORIAL_RESOURCES)
LEGACY_COMPLETION_TITLES = {
    'fixed_trial_2': frozenset({'Accord 90 秒开场稿 · 完成记录', '拍办 90 秒开场稿 · 完成记录'}),
    'fixed_trial_3': frozenset(
        {'Accord 工作台 1440 宽度复核 · 完成记录', '拍办工作台 1440 宽度复核 · 完成记录'}
    ),
}


def _brand_rename(value: str):
    return (
        value.replace('本次 Accord 路演', '本次拍办路演')
        .replace('负责 Accord 的', '负责拍办的')
        .replace('为什么要做 Accord', '为什么要做拍办')
        .replace('在 Accord 中', '在拍办中')
        .replace('Accord 产品', '拍办产品')
        .replace('Accord 工作台', '拍办工作台')
        .replace('Accord 路演', '拍办路演')
        .replace('Accord 面向', '拍办面向')
        .replace('Accord 的', '拍办的')
        .replace('Accord', '拍办')
    )


def _tutorial_copy_upgrade(value: str):
    return (
        _brand_rename(value)
        .replace(
            '任务完成后由负责人勾选，系统依据真实成果生成总结。',
            '任务先由负责人在自己的工作台对话里完成；本人勾选后，系统直接读取这段对话、生成总结并沉淀记忆。',
        )
        .replace(
            '演示结束前是否已准备一份可上传的 UI 复核结果，供任务完成时核验。',
            '演示结束前是否能在体验者三的工作台对话中完成 UI 复核，再由待办整理流程直接读取结果。',
        )
        .replace(
            '完成时还需上传真实复核结果并勾选确认。',
            '完成时还需先在本人的工作台对话里产出真实复核结果，再勾选确认。',
        )
    )


def _migrate_legacy_copy(db, expected: TutorialResource, row):
    current = db.execute(
        'SELECT * FROM accord_resource_versions WHERE resource_id=? AND version=?',
        (expected.id, row['version']),
    ).fetchone()
    if current and current['title'] == expected.title and current['body'] == expected.body:
        return row
    if (
        not current
        or _tutorial_copy_upgrade(current['title']) != expected.title
        or _tutorial_copy_upgrade(current['body']) != expected.body
    ):
        return row
    refs = current['refs']
    next_version = row['version'] + 1
    db.execute(
        'INSERT INTO accord_resource_versions VALUES(?,?,?,?,?,?,?)',
        (
            expected.id,
            next_version,
            expected.title,
            expected.body,
            refs,
            hashlib.sha256((expected.body + refs).encode()).hexdigest(),
            store.now(),
        ),
    )
    db.execute('UPDATE accord_resources SET version=? WHERE id=?', (next_version, expected.id))
    return db.execute('SELECT * FROM accord_resources WHERE id=?', (expected.id,)).fetchone()


def _retire_legacy_completion_resources(db):
    retired = 0
    rows = db.execute(
        """SELECT r.id,r.owner_id,v.title,v.body FROM accord_resources r
        JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
        WHERE r.active=1 AND r.owner_id IN ('fixed_trial_2','fixed_trial_3')"""
    ).fetchall()
    for row in rows:
        titles = LEGACY_COMPLETION_TITLES.get(row['owner_id'], ())
        body = row['body']
        product_copy = row['owner_id'] == 'fixed_trial_2' and all(
            marker in body for marker in ('关联待办：', '## 开场稿', '## 已完成')
        )
        ui_copy = row['owner_id'] == 'fixed_trial_3' and all(
            marker in body for marker in ('关联待办：', '## 复核结论', '## 已检查')
        )
        if row['title'] in titles and (product_copy or ui_copy):
            db.execute('UPDATE accord_resources SET active=0 WHERE id=?', (row['id'],))
            retired += 1
    return retired


def _assert_existing_resource(db, expected: TutorialResource, row):
    version = db.execute(
        'SELECT * FROM accord_resource_versions WHERE resource_id=? AND version=?',
        (expected.id, row['version']),
    ).fetchone()
    matches = (
        row['owner_id'] == expected.owner_id
        and row['kind'] == 'note'
        and row['scope'] == 'team'
        and row['active'] == 1
        and version
        and version['title'] == expected.title
        and version['body'] == expected.body
        and version['refs'] == '[]'
    )
    if not matches:
        raise DomainError(409, '教学样例标识已被占用，未改写现有资料。')
    return version


def _summary(item: TutorialResource, row, created: bool):
    return {
        'id': item.id,
        'owner_id': item.owner_id,
        'owner_name': item.owner_name,
        'title': item.title,
        'focus': item.focus,
        'scope': row['scope'],
        'kind': row['kind'],
        'version': row['version'],
        'created': created,
    }


def prepare(uid: str):
    if uid not in TRIAL_ACCOUNT_IDS or identity.account_roster(uid) != 'trial':
        raise DomainError(403, '仅体验账号可以准备教学演练资料。')

    resources = []
    created_count = 0
    with store.lock, store.connection() as db:
        retired_completion_count = _retire_legacy_completion_resources(db)
        for item in TUTORIAL_RESOURCES:
            row = db.execute('SELECT * FROM accord_resources WHERE id=?', (item.id,)).fetchone()
            created = row is None
            if created:
                create_resource(
                    db,
                    item.owner_id,
                    item.title,
                    item.body,
                    scope='team',
                    kind='note',
                    resource_id=item.id,
                )
                row = db.execute('SELECT * FROM accord_resources WHERE id=?', (item.id,)).fetchone()
                created_count += 1
            else:
                row = _migrate_legacy_copy(db, item, row)
            _assert_existing_resource(db, item, row)
            resources.append(_summary(item, row, created))

        fixture = exploration_fixture.ensure(db)

        while index.synchronize(db):
            pass

    return {
        'ready': True,
        'created_count': created_count,
        'retired_completion_count': retired_completion_count,
        'resources': resources,
        'exploration_fixture': fixture,
    }


def reset_exploration(uid, body):
    return exploration_fixture.reset(uid, body)
