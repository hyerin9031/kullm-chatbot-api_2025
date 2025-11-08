import requests
import json
from typing import List, Dict
import random
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import os

# ============================
# 1. 온통청년 API 연동
# ============================

class YouthPolicyAPI:
    def __init__(self, api_key: str):
        self.api_url = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
        self.api_key = api_key

    def get_policies(self, page_num: int = 1, page_size: int = 100) -> Dict:
        params = {
            "apiKeyNm": self.api_key,
            "pageNum": page_num,
            "pageSize": page_size,
            "rtnType": "json"
        }
        try:
            response = requests.get(self.api_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception as e:
            print(f"온통청년 API 오류: {e}")
            return None

    def search_policies(self, age: int = None, region: str = None, 
                       keyword: str = None, max_results: int = 3, all_ages: bool = False) -> List[Dict]:
        data = self.get_policies(page_size=100)
        if not data or 'result' not in data:
            return []

        policies = data['result'].get('youthPolicyList', [])
        filtered_policies = []

        for policy in policies:
            # 나이 필터링
            if age or all_ages:
                try:
                    min_age = int(policy.get('sprtTrgtMinAge', 0))
                    max_age = int(policy.get('sprtTrgtMaxAge', 999))
                    if min_age < 0 or max_age > 120:
                        continue
                    if all_ages:
                        if max_age - min_age < 50:
                            continue
                    elif age and not (min_age <= age <= max_age):
                        continue
                except:
                    pass

            # 지역 필터링
            if region:
                inst_name = policy.get('rgtrInstCdNm', '')
                region_mapping = {
                    '서울': ['서울'], '부산': ['부산'], '대구': ['대구'], 
                    '창원': ['창원'], '경남': ['경상남도', '경남']
                }
                match_regions = region_mapping.get(region, [region])
                if not any(r in inst_name for r in match_regions):
                    continue

            # 키워드 필터링
            if keyword:
                policy_name = policy.get('plcyNm', '')
                policy_content = policy.get('plcyExplnCn', '')
                if keyword not in policy_name and keyword not in policy_content:
                    continue

            policy['source'] = '온통청년'
            filtered_policies.append(policy)

        if len(filtered_policies) > max_results:
            random.shuffle(filtered_policies)
            filtered_policies = filtered_policies[:max_results]

        return filtered_policies

    def format_policy(self, policy: Dict) -> str:
        return f"""
📌 **{policy.get('plcyNm', '정책명 없음')}** [온통청년]

🏢 주관기관: {policy.get('sprvsnInstCdNm', '정보 없음')}
📅 신청기간: {policy.get('aplyYmd', '상시 신청 가능')}
👥 나이: {policy.get('sprtTrgtMinAge', '?')}세 ~ {policy.get('sprtTrgtMaxAge', '?')}세

🔗 상세정보: {policy.get('refUrlAddr1', '링크 없음')}
{'='*80}
"""

# ============================
# 2. 기업마당 API 연동
# ============================

class BizinfoPolicyAPI:
    def __init__(self, api_key: str):
        self.api_url = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
        self.api_key = api_key

    def get_policies(self, max_count: int = 100) -> List[Dict]:
        params = {
            "crtfcKey": self.api_key,
            "dataType": "json",
            "pageUnit": max_count,
            "pageIndex": 1
        }
        try:
            response = requests.get(self.api_url, params=params, timeout=20)
            if response.status_code != 200:
                return []
            data = response.json()
            items = data.get("jsonArray", {}).get("item", [])
            policies = []
            for item in items:
                policy = {
                    "title": item.get("pblancNm", "N/A"),
                    "agency": item.get("jrsdInsttNm", "N/A"),
                    "url": "https://www.bizinfo.go.kr" + item.get("pblancUrl", ""),
                    "source": "기업마당"
                }
                policies.append(policy)
            return policies
        except Exception as e:
            print(f"기업마당 API 오류: {e}")
            return []

    def search_policies(self, keyword: str = None, max_results: int = 3) -> List[Dict]:
        all_policies = self.get_policies()
        filtered = []
        for policy in all_policies:
            if keyword and keyword.lower() not in policy["title"].lower():
                continue
            filtered.append(policy)
        if len(filtered) > max_results:
            random.shuffle(filtered)
            filtered = filtered[:max_results]
        return filtered

    def format_policy(self, policy: Dict) -> str:
        return f"""
🏢 **{policy["title"]}** [기업마당]

기관: {policy["agency"]}

🔗 상세 보기: {policy["url"]}
{'='*80}
"""

# ============================
# 3. 알리오 플러스 API
# ============================

class AlioplusPolicyAPI:
    def __init__(self, api_key: str):
        self.api_url = "http://openapi.alioplus.go.kr/api/business"
        self.api_key = api_key.replace("+", "%2B")

    def get_policies(self, max_count: int = 100) -> List[Dict]:
        params = {"X-API-AUTH-KEY": self.api_key, "pageSize": str(max_count)}
        try:
            response = requests.post(self.api_url, data=params, timeout=20)
            if response.status_code != 200:
                return []
            data = response.json()
            items = data.get('list', []) if isinstance(data, dict) else []
            policies = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                policy = {
                    "title": item.get("bsnNa", "N/A"),
                    "agency": item.get("apbaNa", "N/A"),
                    "url": item.get("siteUrl", ""),
                    "source": "알리오플러스"
                }
                policies.append(policy)
            return policies
        except Exception as e:
            print(f"알리오플러스 API 오류: {e}")
            return []

    def search_policies(self, keyword: str = None, max_results: int = 2) -> List[Dict]:
        all_policies = self.get_policies()
        filtered = []
        for policy in all_policies:
            if keyword and keyword.lower() not in policy["title"].lower():
                continue
            filtered.append(policy)
        if len(filtered) > max_results:
            random.shuffle(filtered)
            filtered = filtered[:max_results]
        return filtered

    def format_policy(self, policy: Dict) -> str:
        return f"""
🛍️ **{policy["title"]}** [알리오플러스]

기관: {policy["agency"]}

🔗 상세 보기: {policy["url"] if policy["url"] else "정보 없음"}
{'='*80}
"""

# ============================
# 4. KULLM Inference API
# ============================

class KULLMInferenceAPI:
    """✅ Hugging Face Inference API로 KULLM 호출"""
    def __init__(self, model_name: str = "nlpai-lab/KULLM-Polyglot-5.8B-v2", hf_token: str = None):
        self.api_url = f"https://api-inference.huggingface.co/models/{model_name}"
        self.headers = {}
        if hf_token:
            self.headers["Authorization"] = f"Bearer {hf_token}"
        print(f"✅ KULLM Inference API 초기화: {model_name}")

    def generate_response(self, prompt: str, max_new_tokens: int = 120, max_retries: int = 2) -> str:
        """Inference API로 응답 생성 (재시도 로직 포함)"""
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": 0.6,
                "top_p": 0.9,
                "do_sample": True,
                "return_full_text": False,
                "repetition_penalty": 1.12
            }
        }

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 503:
                    if attempt < max_retries - 1:
                        print(f"⏳ 모델 로딩 중... 재시도 {attempt+1}/{max_retries}")
                        import time
                        time.sleep(20)
                        continue
                    return "⏳ 모델이 로딩 중입니다. 잠시 후 다시 시도해주세요."
                
                response.raise_for_status()
                result = response.json()
                
                if isinstance(result, list) and len(result) > 0:
                    text = result[0].get('generated_text', '')
                    return self.clean_response(text)
                
                return "응답을 생성하지 못했습니다."

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    print(f"⏱️ 타임아웃... 재시도 {attempt+1}/{max_retries}")
                    continue
                return "⏱️ 응답 시간이 초과되었습니다."
            except Exception as e:
                print(f"KULLM API 오류: {e}")
                return "죄송합니다. 응답 생성 중 문제가 발생했습니다."

        return "응답 생성에 실패했습니다."

    def clean_response(self, text: str) -> str:
        """응답 정리"""
        patterns = [
            r'\b(User|사용자)\s*:\s*.*?\n',
            r'\b(Assistant|Chatbot|챗봇)\s*:\s*',
        ]
        for p in patterns:
            text = re.sub(p, '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text if text else "더 구체적으로 질문해주시면 도움을 드리겠습니다."

# ============================
# 5. 통합 챗봇
# ============================

class UnifiedPolicyChatbot:
    def __init__(self, youth_api_key: str, bizinfo_api_key: str, alioplus_api_key: str, hf_token: str = None):
        self.youth_api = YouthPolicyAPI(youth_api_key)
        self.bizinfo_api = BizinfoPolicyAPI(bizinfo_api_key)
        self.alioplus_api = AlioplusPolicyAPI(alioplus_api_key)
        self.kullm = KULLMInferenceAPI(hf_token=hf_token)
        print("✅ 챗봇 초기화 완료!")

    def extract_user_info(self, message: str) -> Dict:
        """사용자 정보 추출"""
        info = {
            'age': None,
            'region': None,
            'keyword': None,
            'explicit_search': False,
            'max_results': 3
        }

        # 정책 개수 추출
        count_match = re.search(r'(\d+)개', message)
        if count_match:
            requested_count = int(count_match.group(1))
            if 1 <= requested_count <= 20:
                info['max_results'] = requested_count

        # 나이 추출
        age_patterns = [(r'(\d{2})살', 'exact'), (r'(\d{2})세', 'exact')]
        for pattern, _ in age_patterns:
            match = re.search(pattern, message)
            if match:
                age_val = int(match.group(1))
                if 0 <= age_val <= 120:
                    info['age'] = age_val
                    break

        # 지역 추출
        regions = ['서울', '부산', '대구', '창원', '경남', '경기', '제주']
        for region in regions:
            if region in message:
                info['region'] = region
                break

        # 키워드 추출
        keywords = ['창업', '취업', '주거', '자격증', '대출', '교육', 'R&D', '일자리']
        for kw in keywords:
            if kw in message:
                info['keyword'] = kw
                break

        # 명시적 검색 감지
        policy_keywords = ['정책', '지원', '사업', '프로그램']
        search_verbs = ['찾아', '검색', '뽑아', '추천', '보여']
        
        has_policy = any(kw in message for kw in policy_keywords)
        has_search = any(verb in message for verb in search_verbs)
        
        info['explicit_search'] = (has_policy and has_search) or \
                                  (has_policy and (info['age'] or info['region'] or info['keyword']))

        return info

    def search_policies(self, user_info: Dict) -> str:
        """정책 검색"""
        all_policies = []
        max_results = user_info.get('max_results', 3)
        
        # 청년 정책
        if user_info.get('age') is None or user_info.get('age') <= 39:
            youth_policies = self.youth_api.search_policies(
                age=user_info.get('age'),
                region=user_info.get('region'),
                keyword=user_info.get('keyword'),
                max_results=max_results * 2
            )
            all_policies.extend(youth_policies)

        # 기업 정책
        bizinfo_policies = self.bizinfo_api.search_policies(
            keyword=user_info.get('keyword'),
            max_results=max_results * 2
        )
        all_policies.extend(bizinfo_policies)

        alioplus_policies = self.alioplus_api.search_policies(
            keyword=user_info.get('keyword'),
            max_results=max_results
        )
        all_policies.extend(alioplus_policies)
        
        # 중복 제거
        seen_urls = set()
        unique_policies = []
        for policy in all_policies:
            url = policy.get('refUrlAddr1') or policy.get('url')
            if url and url not in seen_urls:
                unique_policies.append(policy)
                seen_urls.add(url)
            elif not url:
                unique_policies.append(policy)

        if len(unique_policies) > max_results:
            random.shuffle(unique_policies)
            unique_policies = unique_policies[:max_results]

        if not unique_policies:
            return ""

        result = f"\n\n✨ **관련 정책 {len(unique_policies)}개:**\n"
        for policy in unique_policies:
            source = policy.get('source', '')
            if source == '온통청년':
                result += self.youth_api.format_policy(policy)
            elif source == '기업마당':
                result += self.bizinfo_api.format_policy(policy)
            elif source == '알리오플러스':
                result += self.alioplus_api.format_policy(policy)

        return result

    def chat(self, message: str) -> str:
        """챗봇 메인 로직"""
        if message.strip() in ['안녕', '안녕하세요']:
            return "안녕하세요! 😊 청년 및 기업 정책 추천 챗봇입니다.\n무엇을 도와드릴까요?"

        user_info = self.extract_user_info(message)

        # 명시적 검색
        if user_info['explicit_search']:
            policy_results = self.search_policies(user_info)
            if policy_results:
                return "관련 정책을 찾아드렸습니다!" + policy_results
            else:
                return "조건에 맞는 정책을 찾지 못했습니다."

        # KULLM 일반 대화
        prompt = (
            "너는 한국어로 자연스럽게 답하는 정책 안내 AI다. "
            "자문자답이나 역할 표시 없이, 완전한 문장으로 답해라.\n\n"
            f"질문: {message}\n\n답변:"
        )
        return self.kullm.generate_response(prompt, max_new_tokens=120)

# ============================
# 6. Flask API
# ============================

app = Flask(__name__)
CORS(app)  # ✅ CORS 활성화 (외부 웹사이트에서 접근 가능)

# 전역 챗봇 인스턴스
global_chatbot = None

@app.route("/")
def home():
    return jsonify({
        "service": "통합 정책 추천 챗봇 API",
        "version": "2.0",
        "endpoints": {
            "chat": "/api/chat (POST)",
            "health": "/health (GET)"
        }
    })

@app.route("/health")
def health():
    """헬스 체크"""
    return jsonify({"status": "ok", "chatbot_ready": global_chatbot is not None})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """✅ 메인 챗봇 API 엔드포인트"""
    global global_chatbot
    
    if global_chatbot is None:
        return jsonify({
            "error": "Chatbot not initialized",
            "status": "error"
        }), 500
    
    # JSON 요청 파싱
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({
            "error": "Missing 'message' parameter",
            "status": "error"
        }), 400
    
    user_message = data["message"]
    
    try:
        # 챗봇 응답 생성
        response = global_chatbot.chat(user_message)
        
        return jsonify({
            "response": response,
            "status": "success"
        })
        
    except Exception as e:
        print(f"❌ API 오류: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

# ============================
# 7. 메인 실행
# ============================

if __name__ == "__main__":
    # 환경 변수 또는 기본값
    YOUTH_API_KEY = os.environ.get("YOUTH_API_KEY", "fa19e38e-58a0-4847-b18a-a8e272bd8f40")
    BIZINFO_API_KEY = os.environ.get("BIZINFO_API_KEY", "gQ0k25")
    ALIOPLUS_API_KEY = os.environ.get("ALIOPLUS_API_KEY", "XUUrvIcCpSVWkp0wLH8gPebTAOIJLfwmTgdWoEcFUSQ=")
    HF_TOKEN = os.environ.get("HF_TOKEN")  # 선택사항
    
    print("\n" + "="*60)
    print("🚀 통합 정책 추천 챗봇 API 서버 시작")
    print("="*60)
    
    # 챗봇 초기화
    global_chatbot = UnifiedPolicyChatbot(
        YOUTH_API_KEY,
        BIZINFO_API_KEY,
        ALIOPLUS_API_KEY,
        hf_token=HF_TOKEN
    )
    
    # Flask 서버 실행
    port = int(os.environ.get("PORT", 8000))
    print(f"\n✅ 서버 실행 중: http://0.0.0.0:{port}")
    print(f"✅ API 엔드포인트: http://0.0.0.0:{port}/api/chat")
    print("="*60 + "\n")
    
    app.run(host="0.0.0.0", port=port, debug=False)