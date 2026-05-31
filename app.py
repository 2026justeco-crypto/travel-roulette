import datetime
import hashlib
import hmac
import os
import random
import urllib.parse
import uuid as uuid_lib

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request
from supabase import create_client

load_dotenv()

app = Flask(__name__)

# ─────────────────────────────────────────────
#  Supabase クライアント
# ─────────────────────────────────────────────
_supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)

# ─────────────────────────────────────────────
#  定数（data.py から移動）
# ─────────────────────────────────────────────
REGION_ORDER = ["北海道", "東北", "関東", "中部", "近畿", "中国", "四国", "九州", "沖縄"]
ALL_REGIONS = ["全国"] + REGION_ORDER
SEASON_EMOJI = {"春": "🌸", "夏": "☀️", "秋": "🍁", "冬": "❄️"}
CATEGORY_EMOJI = {
    "歴史・文化": "🏯",
    "自然・絶景": "🏔️",
    "アウトドア": "🥾",
    "グルメ": "🍜",
    "温泉・癒し": "♨️",
    "世界遺産": "🌏",
    "夜景": "🌃",
}

# ─────────────────────────────────────────────
#  スポットキャッシュ（起動時に全件ロード）
# ─────────────────────────────────────────────
SPOTS: list[dict] = []
ALL_CATEGORIES: list[str] = []


def _load_spots() -> None:
    global SPOTS, ALL_CATEGORIES
    res = _supabase.table("spots").select("*").order("id").execute()
    spots = res.data or []
    for s in spots:
        s["desc"] = s.pop("description", "")
    SPOTS = spots
    ALL_CATEGORIES = sorted({cat for s in spots for cat in s.get("category", [])})


_load_spots()


# ─────────────────────────────────────────────
#  ヘルパー: 都道府県名（短縮）を取得
# ─────────────────────────────────────────────
def get_pref_short(pref):
    return pref.split()[0] if " " in pref else pref.split("・")[0]


# ─────────────────────────────────────────────
#  ヘルパー: 拡張説明文の生成（300 文字以上）
# ─────────────────────────────────────────────
def generate_extended_desc(spot):
    name = spot["name"]
    pref = spot["pref"]
    region = spot["region"]
    categories = spot["category"]
    seasons = spot.get("seasons", [])
    desc = spot.get("desc", "")
    highlights = spot.get("highlights", [])
    pref_short = get_pref_short(pref)

    season_label = {
        "春": "春（3〜5月）",
        "夏": "夏（6〜8月）",
        "秋": "秋（9〜11月）",
        "冬": "冬（12〜2月）",
    }
    cat_flavor = {
        "歴史・文化": "日本の歴史と伝統文化が息づく",
        "自然・絶景": "壮大な自然景観が広がる",
        "アウトドア": "アウトドアアクティビティが充実した",
        "グルメ": "地元の食文化と名物グルメが魅力の",
        "温泉・癒し": "疲れを癒す温泉と湯の文化が楽しめる",
        "世界遺産": "ユネスコ世界遺産に登録された",
        "夜景": "幻想的な夜景が楽しめる",
    }

    paragraphs = [desc]

    if highlights:
        hl_str = " / ".join(highlights[:4])
        flavor = cat_flavor.get(categories[0], "多くの旅行者を惹きつける") if categories else "人気の"
        paragraphs.append(
            f"主な見どころには「{hl_str}」などがあります。"
            f"{name}は{flavor}スポットとして{pref_short}を代表する観光地のひとつであり、"
            f"国内外から年間を通じて多くの旅行者が訪れます。"
            f"旅行の目的に合わせてさまざまな楽しみ方ができるため、"
            f"初めての方にも、リピーターにも満足度の高い場所として知られています。"
        )

    if seasons:
        season_strs = [season_label.get(s, s) for s in seasons]
        if len(seasons) >= 4:
            para3 = (
                f"一年を通じて観光を楽しめるスポットですが、特に"
                f"{season_strs[0]}と{season_strs[1]}は見どころが多く、"
                f"多くの観光客で賑わいます。"
            )
        elif len(seasons) == 1:
            para3 = (
                f"おすすめの訪問シーズンは{season_strs[0]}です。"
                f"この時期ならではの景色・体験が{name}の最大の魅力を引き出してくれます。"
            )
        else:
            para3 = (
                f"おすすめの訪問シーズンは{'と'.join(season_strs)}です。"
                f"訪れる時期によって表情を変えるこの場所は、"
                f"何度でも新たな発見がある観光地です。"
            )
        para3 += (
            f"お出かけ前には最新の開館・開園情報や混雑状況を"
            f"各施設の公式サイトや観光協会のホームページでご確認ください。"
        )
        paragraphs.append(para3)

    return "\n\n".join(paragraphs)


# ─────────────────────────────────────────────
#  ヘルパー: 今月のおすすめスポット
# ─────────────────────────────────────────────
def get_recommended_spots(n=5):
    month = datetime.datetime.now().month
    season_map = {
        12: "冬", 1: "冬", 2: "冬",
        3: "春", 4: "春", 5: "春",
        6: "夏", 7: "夏", 8: "夏",
        9: "秋", 10: "秋", 11: "秋",
    }
    current_season = season_map.get(month, "春")
    season_spots = [s for s in SPOTS if current_season in s.get("seasons", [])]

    regions_covered = set()
    recommended = []
    for s in season_spots:
        if s["region"] not in regions_covered and len(recommended) < n:
            recommended.append(s)
            regions_covered.add(s["region"])

    if len(recommended) < n:
        for s in season_spots:
            if s not in recommended and len(recommended) < n:
                recommended.append(s)

    return recommended, current_season


# ─────────────────────────────────────────────
#  ヘルパー: カテゴリ別代表スポット
# ─────────────────────────────────────────────
def get_category_featured_spots():
    result = {}
    for cat in ALL_CATEGORIES:
        spots_in_cat = [s for s in SPOTS if cat in s["category"]]
        if spots_in_cat:
            result[cat] = spots_in_cat[0]
    return result


# ─────────────────────────────────────────────
#  ヘルパー: フィルタリング
# ─────────────────────────────────────────────
def filter_spots(region, categories, season):
    pool = SPOTS
    if region and region != "全国":
        pool = [s for s in pool if s["region"] == region]
    if categories:
        cat_list = [c.strip() for c in categories.split(",") if c.strip()]
        if cat_list:
            pool = [s for s in pool if any(c in s["category"] for c in cat_list)]
    if season:
        pool = [s for s in pool if season in s["seasons"]]
    return pool


# ─────────────────────────────────────────────
#  ヘルパー: スポット JSON 用データを組み立て
# ─────────────────────────────────────────────
def build_spot_json(spot):
    query = urllib.parse.quote(f"{spot['name']} {spot['pref']}")
    pref_name = get_pref_short(spot["pref"])
    jalan_url = "https://www.jalan.net/yad/?CenS=1&keyword=" + urllib.parse.quote(pref_name)
    nearby_details = [
        {
            **s,
            "map_url": f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(s['name'] + ' ' + s['pref'])}",
        }
        for s in SPOTS
        if s["name"] in spot.get("nearby", [])
    ]
    return {
        **spot,
        "map_url": f"https://www.google.com/maps/search/?api=1&query={query}",
        "jalan_url": jalan_url,
        "spot_url": f"/spots/{spot['id']}",
        "nearby_details": nearby_details,
        "rainy_alternatives": spot.get("rainy_alternatives", []),
    }


# ─────────────────────────────────────────────
#  地方・都道府県・カテゴリの説明文
# ─────────────────────────────────────────────
REGION_DESCRIPTIONS = {
    "北海道": "広大な大地と豊かな自然が広がる北海道。四季折々の絶景と新鮮な海の幸・農産物が魅力で、年間を通じて多くの観光客が訪れます。世界自然遺産の知床、ラベンダーの富良野、夜景の函館など、見どころは尽きません。",
    "東北": "豊かな自然と伝統文化が息づく東北地方。青森・岩手・宮城・秋田・山形・福島の6県にまたがり、桜・紅葉・温泉・雪まつりなど四季の見どころが満載です。豊かな食文化（牛タン・わんこそば・芋煮）も旅の醍醐味です。",
    "関東": "首都圏を含む関東地方は、東京の都市文化から日光・箱根の自然まで多彩な観光スポットが集まるエリアです。世界遺産の日光東照宮・富岡製糸場、温泉の草津・伊香保、海鮮グルメの三陸海岸など幅広い魅力があります。",
    "中部": "日本アルプスの雄大な山々、富士山、伊勢神宮など、日本を代表するスポットが集まる中部地方。北陸の海の幸・金沢の伝統文化から、長野の山岳リゾート、東海の歴史文化まで多彩な魅力があります。",
    "近畿": "京都・大阪・奈良など日本の歴史・文化の中心地が集まる近畿地方。世界遺産も多く、古都の風情と現代的な都市文化が共存しています。温泉の有馬・城崎、自然の熊野古道など奥深い魅力も持ちます。",
    "中国": "山陰・山陽に分かれる中国地方は、砂丘・神話の里・世界遺産の厳島神社など個性豊かなスポットが揃います。瀬戸内海の穏やかな景色、出雲の縁結び信仰、広島の歴史と平和の地も見どころです。",
    "四国": "四国八十八か所遍路で有名な四国地方。徳島・香川・愛媛・高知の4県が個性的な観光地を持ち、秘境の祖谷、讃岐うどん、道後温泉、カツオのたたきなど豊かな自然と食文化が楽しめます。",
    "九州": "九州は火山・温泉・歴史遺産の宝庫。福岡の博多グルメから鹿児島の桜島まで、バラエティ豊かな観光スポットが続きます。長崎の異国情緒、熊本の阿蘇山、大分の別府・由布院温泉も人気です。",
    "沖縄": "日本最南端の沖縄は、エメラルドグリーンの海と珊瑚礁が広がるリゾートアイランド。首里城に代表される琉球文化、石垣島・宮古島の離島リゾート、ダイビングなどマリンアクティビティも充実しています。",
}

PREF_DESCRIPTIONS = {
    "北海道": "日本最大の都道府県・北海道には、知床・富良野・函館など絶景スポットが豊富。雄大な自然と新鮮な海の幸・農産物で人気の観光地です。",
    "青森県": "本州最北端の青森県は、ねぶた祭・弘前城・奥入瀬渓谷など個性豊かな観光スポットが揃っています。りんごと海産物も絶品です。",
    "岩手県": "岩手県は世界遺産の平泉・中尊寺金色堂をはじめ、三陸海岸の絶景や豊富な温泉地が魅力。わんこそば・冷麺・じゃじゃ麺の盛岡三大麺も有名です。",
    "宮城県": "東北最大の都市・仙台を擁する宮城県。日本三景の松島、仙台牛タン、鳴子温泉郷など多彩な見どころを持つ観光地です。",
    "秋田県": "秋田県は竿燈まつり・なまはげなど伝統行事と、男鹿半島・田沢湖の自然が魅力。きりたんぽ・稲庭うどんの食文化も有名です。",
    "山形県": "山形県は蔵王の樹氷・銀山温泉・山寺（立石寺）など多彩な見どころが揃います。山形芋煮・さくらんぼ・米沢牛など食の宝庫でもあります。",
    "福島県": "福島県は磐梯山・猪苗代湖・会津若松城などが有名な観光地。白虎隊ゆかりの会津、大内宿の茅葺き宿場町、五色沼の絶景も必訪です。",
    "茨城県": "茨城県には日本三名園の偕楽園、日本三名瀑の袋田の滝など名所が点在。筑波山のハイキングや水戸のグルメも楽しめます。",
    "栃木県": "世界遺産・日光東照宮、足利フラワーパークの大藤、草津・塩原温泉など多彩な観光地が揃う栃木県。宇都宮餃子も定番グルメです。",
    "群馬県": "草津温泉・伊香保温泉・四万温泉と全国屈指の温泉地が揃う群馬県。世界遺産の富岡製糸場、尾瀬ヶ原の自然も魅力的です。",
    "埼玉県": "秩父の三峯神社・長瀞ライン下り、小江戸川越の蔵造り町並みなど関東屈指の観光地を持つ埼玉県。都心からのアクセスも抜群です。",
    "千葉県": "成田山新勝寺、九十九里浜、南房総の花畑など多彩な観光地を誇る千葉県。新鮮な海の幸と温暖な気候も魅力です。",
    "神奈川県": "横浜・みなとみらいの夜景、鎌倉の大仏・江ノ島、箱根の温泉と富士山など、見どころが凝縮した神奈川県。関東随一の人気観光地です。",
    "東京都": "日本の首都・東京は浅草・上野の伝統文化から渋谷・原宿のトレンドまで多彩な顔を持ちます。東京スカイツリーや築地海鮮も人気スポットです。",
    "新潟県": "日本一の米どころ・新潟は日本酒と越後の山海の幸が揃います。佐渡島の世界遺産候補・金山、越後湯沢のスキー、へぎそばも必体験です。",
    "富山県": "立山黒部アルペンルートの雪の大谷、黒部ダムの迫力など山岳観光が有名な富山県。白えびやホタルイカなど富山湾の海の幸も絶品です。",
    "石川県": "日本三名園のひとつ兼六園と近江町市場の海鮮が有名な金沢を擁する石川県。輪島・白米千枚田の棚田など奥能登の自然も見どころです。",
    "福井県": "曹洞宗大本山・永平寺、東尋坊の断崖絶壁、越前ガニが三大名物の福井県。恐竜化石の産地としても世界的に有名です。",
    "山梨県": "富士山の玄関口・山梨県には、河口湖・山中湖などの富士五湖、昇仙峡の絶景が広がります。甲州ワインとほうとうも名物です。",
    "長野県": "上高地・白馬・蓼科など日本アルプスの山岳リゾートが揃う長野県。松本城・善光寺の歴史スポット、信州そばも外せません。",
    "岐阜県": "世界遺産・白川郷合掌造り集落と飛騨高山の古い町並みが有名な岐阜県。飛騨牛・長良川鵜飼・岐阜城など見どころ豊富です。",
    "静岡県": "富士山・富士五湖、熱海・伊豆の温泉リゾート、浜松・浜名湖のうな重と多彩な魅力を持つ静岡県。お茶の生産地としても有名です。",
    "愛知県": "名古屋城・熱田神宮と「名古屋メシ」（ひつまぶし・手羽先・味噌カツ）が有名な愛知県。国宝・犬山城や博物館明治村も必訪スポットです。",
    "三重県": "伊勢神宮（内宮・外宮）を擁する三重県は「日本人の心のふるさと」。伊勢海老・牡蠣、鳥羽水族館、志摩の海も魅力です。",
    "滋賀県": "日本最大の湖・琵琶湖と比叡山延暦寺（世界遺産）、彦根城、近江牛が三大名物の滋賀県。水辺の自然が楽しめる観光地です。",
    "京都府": "千年の都・京都は世界遺産の神社仏閣が点在する日本随一の観光地。嵐山・嵯峨野の竹林、東山・祇園の石畳、京料理と見どころが尽きません。",
    "大阪府": "「食い倒れの街」大阪は道頓堀・通天閣の名物スポットから大阪城の歴史まで多彩な魅力を持ちます。たこ焼き・お好み焼き・串カツも必食です。",
    "兵庫県": "世界遺産・姫路城、神戸の異人館・中華街、有馬温泉、城崎温泉と豊富な見どころを持つ兵庫県。神戸牛も絶品グルメです。",
    "奈良県": "世界遺産の東大寺・興福寺・春日大社が集まる奈良県。シカが闊歩する奈良公園、吉野山の桜、飛鳥の古代遺跡も必訪スポットです。",
    "和歌山県": "世界遺産・高野山と熊野古道を擁する霊場の地・和歌山県。白浜温泉、那智の滝、アドベンチャーワールドのパンダも人気です。",
    "鳥取県": "日本唯一の砂丘・鳥取砂丘と砂の美術館が有名な鳥取県。大山の雄大な山岳風景、松葉がに・二十世紀梨などグルメも充実しています。",
    "島根県": "縁結びの神・出雲大社と世界遺産・石見銀山が有名な島根県。松江城・宍道湖の夕日、足立美術館の日本庭園も見どころです。",
    "岡山県": "日本三名園の後楽園と岡山城、倉敷美観地区の白壁の町並みが有名な岡山県。蒜山高原の自然と蒜山ジャージー牛乳も魅力です。",
    "広島県": "世界遺産の厳島神社（宮島）と原爆ドームを持つ広島県。しまなみ海道サイクリング、尾道の坂道と映画の街、牡蠣料理も必体験です。",
    "山口県": "角島大橋の絶景、錦帯橋の木造橋、萩の幕末遺跡が有名な山口県。秋吉台・秋芳洞の鍾乳洞、ふぐ料理（河豚）も名物です。",
    "徳島県": "阿波踊りと渦潮（鳴門）が有名な徳島県。祖谷のかずら橋・大歩危峡の秘境、すだち・鳴門金時（さつまいも）も名物です。",
    "香川県": "讃岐うどんとこんぴらさん（金刀比羅宮）で有名な香川県。栗林公園の日本庭園、小豆島のオリーブ園、父母ヶ浜の天空の鏡も必訪スポットです。",
    "愛媛県": "道後温泉・松山城の松山、しまなみ海道サイクリング、今治のタオルが有名な愛媛県。みかんの生産量日本一でもあります。",
    "高知県": "坂本龍馬の故郷・高知県には、桂浜の絶景、四万十川の清流、高知城の現存天守が揃います。カツオのたたきと皿鉢料理も絶品です。",
    "福岡県": "九州の玄関口・福岡は博多ラーメン・もつ鍋・屋台文化が有名。大宰府天満宮、柳川の川下り、糸島の自然リゾートも人気スポットです。",
    "佐賀県": "有田焼・唐津焼の陶磁器文化と、吉野ヶ里歴史公園（弥生時代遺跡）が有名な佐賀県。嬉野温泉、呼子のイカ活き造りも絶品です。",
    "長崎県": "日本の開港地として異国情緒あふれる長崎市はグラバー園・出島が有名。軍艦島クルーズ、ハウステンボス、五島列島の離島も人気です。",
    "熊本県": "加藤清正が築いた熊本城と阿蘇山の雄大な火山景観が魅力の熊本県。天草の崎津集落（世界遺産）、黒川温泉、馬刺しも必体験です。",
    "大分県": "「おんせん県おおいた」として知られる大分県は別府・由布院の温泉天国。耶馬渓の絶景、臼杵石仏、関サバ・関アジも有名です。",
    "宮崎県": "高千穂峡の神秘的な渓谷と青島神社が有名な宮崎県。日向灘の青い海、霧島山系の雄大な景観、宮崎地鶏・マンゴーも名物です。",
    "鹿児島県": "桜島の活火山と指宿の砂むし温泉が有名な鹿児島県。世界遺産・屋久島の縄文杉、奄美大島の亜熱帯自然、知覧特攻平和会館も必訪です。",
    "沖縄県": "美ら海水族館・首里城をはじめ、石垣島・宮古島の離島リゾートが揃う沖縄県。ダイビング・スノーケリングなどマリンスポーツも充実しています。",
}

CATEGORY_DESCRIPTIONS = {
    "歴史・文化": "日本の歴史と伝統文化が感じられるスポットを集めました。城郭・神社仏閣・伝統的な町並みなど、日本の長い歴史を肌で感じることができる場所ばかりです。ガイドブックには載りきらない深い歴史的背景を持つ観光地を全国から厳選しています。",
    "自然・絶景": "日本が誇る絶景の自然スポットを全国から集めました。山・川・海・湖など、息をのむような美しい景色が楽しめる場所ばかりです。四季ごとに変わる表情も魅力のひとつ。雄大な自然の中で日常を忘れるひとときをお過ごしください。",
    "アウトドア": "登山・ハイキング・カヌーなど、アクティビティが充実したスポットを厳選しました。日本の豊かな自然の中で体を動かす旅は格別です。初心者から上級者まで楽しめるコースが揃っており、家族や友人グループにもおすすめです。",
    "グルメ": "地域の名物料理・食文化が楽しめるスポットを全国から集めました。海鮮・郷土料理・スイーツなど、旅の醍醐味であるグルメ体験ができる場所ばかりです。「食べなければ損」と言われる地域の絶品グルメを目当てに旅をするのも、素晴らしい旅の形です。",
    "温泉・癒し": "全国の名湯・秘湯・温泉地を集めました。疲れた体と心を癒す温泉旅行の参考にどうぞ。泉質・景観・宿の雰囲気はそれぞれ異なり、同じ温泉でも季節や時間帯によって違う表情が楽しめます。日本が世界に誇る温泉文化をぜひ体験してください。",
    "世界遺産": "ユネスコが認定した日本の世界遺産スポットを集めました。自然遺産・文化遺産ともに、世界に誇る日本の宝を訪れることができます。世界遺産登録の背景や歴史を学びながら巡る旅は、単なる観光を超えた深い体験を与えてくれるでしょう。",
    "夜景": "日本の美しい夜景スポットを集めました。函館・長崎・神戸など「日本三大夜景」をはじめ、各地の輝く夜の絶景をお楽しみください。都市の夜景だけでなく、温泉地の灯りや海辺の夜景など、さまざまな種類の夜景スポットを掲載しています。",
}


# ─────────────────────────────────────────────
#  ページルート
# ─────────────────────────────────────────────
@app.route("/")
def index():
    recommended_spots, current_season = get_recommended_spots(5)
    category_featured = get_category_featured_spots()
    month = datetime.datetime.now().month
    return render_template(
        "index.html",
        regions=ALL_REGIONS,
        categories=ALL_CATEGORIES,
        category_emoji=CATEGORY_EMOJI,
        season_emoji=SEASON_EMOJI,
        recommended_spots=recommended_spots,
        category_featured=category_featured,
        current_season=current_season,
        current_month=month,
    )


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/ads.txt")
def ads_txt():
    content = "google.com, pub-5689524720836884, DIRECT, f08c47fec0942fa0\n"
    return content, 200, {"Content-Type": "text/plain; charset=utf-8"}


# ─────────────────────────────────────────────
#  スポット詳細ページ
# ─────────────────────────────────────────────
@app.route("/spots/<int:spot_id>")
def spot_detail(spot_id):
    spot = next((s for s in SPOTS if s["id"] == spot_id), None)
    if spot is None:
        abort(404)

    pref_short = get_pref_short(spot["pref"])

    related_pref = [
        s for s in SPOTS
        if get_pref_short(s["pref"]) == pref_short and s["id"] != spot_id
    ][:4]

    related_pref_ids = {s["id"] for s in related_pref}
    related_cat = [
        s for s in SPOTS
        if any(c in spot["category"] for c in s["category"])
        and s["id"] != spot_id
        and s["id"] not in related_pref_ids
    ][:4]

    map_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(spot['name'] + ' ' + spot['pref'])}"
    jalan_url = "https://www.jalan.net/yad/?CenS=1&keyword=" + urllib.parse.quote(pref_short)
    nearby_details = [s for s in SPOTS if s["name"] in spot.get("nearby", [])]
    extended_desc = generate_extended_desc(spot)

    breadcrumb = [
        ("ホーム", "/"),
        (spot["region"], f"/spots/region/{urllib.parse.quote(spot['region'])}"),
        (pref_short, f"/spots/prefecture/{urllib.parse.quote(pref_short)}"),
        (spot["name"], None),
    ]

    return render_template(
        "spot_detail.html",
        spot=spot,
        spot_id=spot_id,
        related_pref=related_pref,
        related_cat=related_cat,
        map_url=map_url,
        jalan_url=jalan_url,
        nearby_details=nearby_details,
        extended_desc=extended_desc,
        breadcrumb=breadcrumb,
        category_emoji=CATEGORY_EMOJI,
        season_emoji=SEASON_EMOJI,
        pref_short=pref_short,
    )


# ─────────────────────────────────────────────
#  地方別一覧ページ
# ─────────────────────────────────────────────
@app.route("/spots/region/<path:region_name>")
def spots_region(region_name):
    decoded = urllib.parse.unquote(region_name)
    matched = next((r for r in REGION_ORDER if r == decoded), None)
    if not matched:
        abort(404)

    spots = [s for s in SPOTS if s["region"] == matched]
    prefs = sorted(set(get_pref_short(s["pref"]) for s in spots))
    description = REGION_DESCRIPTIONS.get(matched, f"{matched}地方の観光スポット一覧です。")

    return render_template(
        "spots_region.html",
        region=matched,
        spots=spots,
        prefs=prefs,
        description=description,
        category_emoji=CATEGORY_EMOJI,
        season_emoji=SEASON_EMOJI,
        region_order=REGION_ORDER,
    )


# ─────────────────────────────────────────────
#  都道府県別一覧ページ
# ─────────────────────────────────────────────
@app.route("/spots/prefecture/<path:pref_name>")
def spots_prefecture(pref_name):
    decoded = urllib.parse.unquote(pref_name)
    spots = [s for s in SPOTS if get_pref_short(s["pref"]) == decoded]
    if not spots:
        abort(404)

    region = spots[0]["region"]
    description = PREF_DESCRIPTIONS.get(decoded, f"{decoded}の観光スポット一覧です。地域の名所・グルメ・自然を楽しめるスポットを集めました。")

    return render_template(
        "spots_prefecture.html",
        pref=decoded,
        spots=spots,
        region=region,
        description=description,
        category_emoji=CATEGORY_EMOJI,
        season_emoji=SEASON_EMOJI,
    )


# ─────────────────────────────────────────────
#  カテゴリ別一覧ページ
# ─────────────────────────────────────────────
@app.route("/spots/category/<path:cat_name>")
def spots_category(cat_name):
    decoded = urllib.parse.unquote(cat_name)
    spots = [s for s in SPOTS if decoded in s["category"]]
    if not spots:
        abort(404)

    description = CATEGORY_DESCRIPTIONS.get(decoded, f"「{decoded}」カテゴリの観光スポット一覧です。")

    return render_template(
        "spots_category.html",
        category=decoded,
        spots=spots,
        description=description,
        category_emoji=CATEGORY_EMOJI,
        season_emoji=SEASON_EMOJI,
    )


# ─────────────────────────────────────────────
#  API: ランダム・スポット検索
# ─────────────────────────────────────────────
@app.route("/api/random")
def api_random():
    region = request.args.get("region", "全国")
    categories = request.args.get("category", "")
    season = request.args.get("season", "")
    pool = filter_spots(region, categories, season)
    if not pool:
        return jsonify({"error": "条件に合うスポットが見つかりません。"}), 404
    spot = random.choice(pool)
    return jsonify(build_spot_json(spot))


@app.route("/api/spot_by_name")
def api_spot_by_name():
    name = request.args.get("name", "")
    spot = next((s for s in SPOTS if s["name"] == name), None)
    if not spot:
        return jsonify({"error": "スポットが見つかりません。"}), 404
    return jsonify(build_spot_json(spot))


@app.route("/api/spots")
def api_spots():
    region = request.args.get("region", "全国")
    categories = request.args.get("category", "")
    season = request.args.get("season", "")
    pool = filter_spots(region, categories, season)
    if not pool:
        return jsonify({"error": "条件に合うスポットが見つかりません。"}), 404

    if region and region != "全国":
        grouped = {region: pool}
    else:
        grouped = {}
        for r in REGION_ORDER:
            spots_in_r = [s for s in pool if s["region"] == r]
            if spots_in_r:
                grouped[r] = spots_in_r

    result = {}
    for region_name, spots in grouped.items():
        result[region_name] = [build_spot_json(s) for s in spots]

    return jsonify({"regions": result, "total": len(pool)})


# ─────────────────────────────────────────────
#  API: 旅の声（匿名投稿）
# ─────────────────────────────────────────────
def _make_delete_token(post_id: int, created_at: str) -> str:
    key = os.environ.get("ADMIN_SECRET", "fallback").encode()
    msg = f"{post_id}:{created_at}".encode()
    return hmac.new(key, msg, "sha256").hexdigest()[:24]


@app.route("/api/posts/<int:spot_id>", methods=["GET"])
def get_posts(spot_id):
    res = (
        _supabase.table("posts")
        .select("id, content, created_at, photo_urls")
        .eq("spot_id", spot_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return jsonify(res.data or [])


def _upload_photo(file) -> str | None:
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        return None
    data = file.read()
    if len(data) > 5 * 1024 * 1024:
        return None
    try:
        path = f"posts/{uuid_lib.uuid4()}.{ext}"
        _supabase.storage.from_("post-photos").upload(
            path, data, {"content-type": file.content_type or f"image/{ext}"}
        )
        return _supabase.storage.from_("post-photos").get_public_url(path)
    except Exception:
        return None


@app.route("/api/posts", methods=["POST"])
def create_post():
    is_multipart = request.content_type and "multipart" in request.content_type
    if is_multipart:
        sid = request.form.get("spot_id", "")
        spot_id = int(sid) if sid.isdigit() else None
        content = (request.form.get("content") or "").strip()
        photo_files = request.files.getlist("photos")[:4]
    else:
        data = request.get_json(silent=True) or {}
        spot_id = data.get("spot_id")
        content = (data.get("content") or "").strip()
        photo_files = []

    if not spot_id or not content:
        return jsonify({"error": "必須項目が不足しています"}), 400
    if len(content) > 100:
        return jsonify({"error": "100文字以内で入力してください"}), 400

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()

    since = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
    count_res = (
        _supabase.table("posts")
        .select("id", count="exact")
        .eq("ip_hash", ip_hash)
        .gte("created_at", since)
        .execute()
    )
    if (count_res.count or 0) >= 5:
        return jsonify({"error": "1日の投稿上限（5件）に達しました。明日またお試しください。"}), 429

    photo_urls = []
    for f in photo_files:
        if f and f.filename:
            url = _upload_photo(f)
            if url:
                photo_urls.append(url)

    result = _supabase.table("posts").insert({
        "spot_id": spot_id,
        "content": content,
        "ip_hash": ip_hash,
        "photo_urls": photo_urls,
    }).execute()

    post = result.data[0]
    token = _make_delete_token(post["id"], post["created_at"])
    return jsonify({"status": "ok", "id": post["id"], "created_at": post["created_at"], "delete_token": token})


@app.route("/api/posts/<int:post_id>", methods=["DELETE"])
def delete_post(post_id):
    token = request.args.get("token", "")
    if not token:
        return jsonify({"error": "トークンが必要です"}), 400

    res = _supabase.table("posts").select("id, created_at").eq("id", post_id).execute()
    if not res.data:
        return jsonify({"error": "投稿が見つかりません"}), 404

    expected = _make_delete_token(post_id, res.data[0]["created_at"])
    if not hmac.compare_digest(token, expected):
        return jsonify({"error": "削除権限がありません"}), 403

    _supabase.table("posts").delete().eq("id", post_id).execute()
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────
#  API: スポット提案フォーム
# ─────────────────────────────────────────────
@app.route("/api/suggestions", methods=["POST"])
def create_suggestion():
    data = request.get_json(silent=True) or {}
    spot_name = (data.get("spot_name") or "").strip()
    near_spot = (data.get("near_spot") or "").strip()
    desc = (data.get("desc") or "").strip()

    if not spot_name or not near_spot or not desc:
        return jsonify({"error": "必須項目が不足しています"}), 400
    if len(spot_name) > 50 or len(near_spot) > 50 or len(desc) > 200:
        return jsonify({"error": "入力が長すぎます"}), 400

    _supabase.table("suggestions").insert({
        "spot_name": spot_name,
        "near_spot": near_spot,
        "description": desc,
    }).execute()

    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────
#  管理: スポットキャッシュ手動リフレッシュ
# ─────────────────────────────────────────────
@app.route("/admin/refresh-spots")
def admin_refresh_spots():
    secret = request.args.get("secret", "")
    if not secret or secret != os.environ.get("ADMIN_SECRET", ""):
        abort(403)
    _load_spots()
    return jsonify({"status": "ok", "count": len(SPOTS)})


# ─────────────────────────────────────────────
#  管理: スポット追加フォーム
# ─────────────────────────────────────────────
_ADMIN_CATEGORIES = ["歴史・文化", "自然・絶景", "アウトドア", "グルメ", "温泉・癒し", "世界遺産", "夜景"]
_ADMIN_SEASONS    = ["春", "夏", "秋", "冬"]


def _check_admin():
    secret = request.args.get("secret") or request.form.get("secret", "")
    return secret == os.environ.get("ADMIN_SECRET", "")


@app.route("/admin/spots/new", methods=["GET"])
def admin_spot_new_form():
    if not _check_admin():
        abort(403)
    return render_template("admin_spot_new.html",
                           regions=REGION_ORDER,
                           categories=_ADMIN_CATEGORIES,
                           seasons=_ADMIN_SEASONS,
                           secret=request.args.get("secret", ""))


@app.route("/admin/spots/new", methods=["POST"])
def admin_spot_new():
    if not _check_admin():
        abort(403)

    secret = request.form.get("secret", "")
    ctx = dict(regions=REGION_ORDER, categories=_ADMIN_CATEGORIES,
               seasons=_ADMIN_SEASONS, secret=secret)

    name        = request.form.get("name", "").strip()
    pref        = request.form.get("pref", "").strip()
    region      = request.form.get("region", "").strip()
    desc        = request.form.get("desc", "").strip()
    highlights  = [h.strip() for h in request.form.get("highlights", "").splitlines() if h.strip()]
    category    = request.form.getlist("category")
    seasons_sel = request.form.getlist("seasons")
    link_label  = request.form.get("link_label", "").strip()
    link_url    = request.form.get("link_url", "").strip()

    if not all([name, pref, region, desc, category]):
        return render_template("admin_spot_new.html", error="必須項目を入力してください", **ctx)

    links = [{"label": link_label, "url": link_url}] if link_label and link_url else []

    result = _supabase.table("spots").insert({
        "name":               name,
        "pref":               pref,
        "region":             region,
        "description":        desc,
        "highlights":         highlights,
        "category":           category,
        "seasons":            seasons_sel,
        "links":              links,
        "nearby":             [],
        "rainy_alternatives": [],
    }).execute()

    new_id = result.data[0]["id"]
    _load_spots()

    return render_template("admin_spot_new.html", success=True, new_id=new_id, **ctx)


if __name__ == "__main__":
    app.run(debug=True)
