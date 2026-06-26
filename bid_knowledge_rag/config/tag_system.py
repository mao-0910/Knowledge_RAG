"""标签体系定义"""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TagCategory:
    """标签分类定义"""
    name: str
    description: str
    multiple: bool = True  # 是否支持多选
    tags: list[str] = field(default_factory=list)


# 投标知识库标签体系
TAG_SYSTEM: list[TagCategory] = [
    TagCategory(
        name="行业标签",
        description="适用行业领域",
        multiple=True,
        tags=[
            "政府机关",
            "教育医疗",
            "金融银行",
            "电力能源",
            "交通物流",
            "制造业",
            "互联网",
            "建筑地产",
            "环保水务",
            "通信广电",
            "国防军工",
            "其他",
        ],
    ),
    
    TagCategory(
        name="客户标签",
        description="客户类型分类",
        multiple=True,
        tags=[
            "内部资料",
            "战略客户",
            "大客户",
            "中小客户",
            "国企客户",
            "民企客户",
            "外企客户",
            "政府客户",
        ],
    ),
    
    TagCategory(
        name="项目类型",
        description="项目业务类型",
        multiple=True,
        tags=[
            "软件开发",
            "系统集成",
            "运维服务",
            "咨询服务",
            "数据服务",
            "安全服务",
            "云服务",
            "硬件采购",
            "网络安全",
            "智能化建设",
        ],
    ),
    
    TagCategory(
        name="产品能力",
        description="产品能力分类",
        multiple=True,
        tags=[
            "自有产品",
            "代理产品",
            "解决方案",
            "平台服务",
            "数据中台",
            "业务中台",
            "基础设施",
        ],
    ),
    
    TagCategory(
        name="服务区域",
        description="服务覆盖区域",
        multiple=True,
        tags=[
            "全国",
            "华东",
            "华南",
            "华北",
            "华中",
            "西南",
            "西北",
            "东北",
            "海外",
            "港澳台",
        ],
    ),
    
    TagCategory(
        name="年份",
        description="资料年份",
        multiple=True,
        tags=[
            "2024",
            "2023",
            "2022",
            "2021",
            "2020",
            "2019",
            "2018",
            "更早",
        ],
    ),
    
    TagCategory(
        name="可公开程度",
        description="资料保密等级",
        multiple=False,  # 单选
        tags=[
            "公开",
            "内部",
            "机密",
            "绝密",
        ],
    ),
    
    TagCategory(
        name="适用场景",
        description="适用业务场景",
        multiple=True,
        tags=[
            "技术方案",
            "商务报价",
            "资质证明",
            "业绩展示",
            "人员配置",
            "服务承诺",
            "风险控制",
            "验收标准",
            "项目管理",
            "质量保障",
        ],
    ),
    
    TagCategory(
        name="审核状态",
        description="内容审核状态",
        multiple=False,  # 单选，由系统管理
        tags=[
            "草稿",
            "待审核",
            "审核中",
            "已发布",
            "已下架",
        ],
    ),
    
    TagCategory(
        name="资料类型",
        description="资料文件类型",
        multiple=True,
        tags=[
            "原始文档",
            "整理文档",
            "扫描件",
            "OCR结果",
            "结构化数据",
            "模板文件",
        ],
    ),
]


def get_all_tags() -> dict[str, list[str]]:
    """获取所有标签分类及标签"""
    return {cat.name: cat.tags for cat in TAG_SYSTEM}


def get_tag_category(category_name: str) -> TagCategory | None:
    """根据分类名称获取标签分类"""
    for cat in TAG_SYSTEM:
        if cat.name == category_name:
            return cat
    return None


def is_multiple_select(category_name: str) -> bool:
    """判断标签分类是否支持多选"""
    cat = get_tag_category(category_name)
    return cat.multiple if cat else True


def validate_tags(tags: list[str]) -> tuple[bool, list[str]]:
    """
    验证标签是否合法
    返回：(是否合法, 非法标签列表)
    """
    all_valid_tags = set()
    for cat in TAG_SYSTEM:
        all_valid_tags.update(cat.tags)
    
    invalid_tags = [tag for tag in tags if tag not in all_valid_tags]
    return len(invalid_tags) == 0, invalid_tags
