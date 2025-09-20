import streamlit as st
import random
import requests
import json
from streamlit_calendar import calendar
from datetime import datetime
from xml.etree import ElementTree as ET

#-----------------------------------------------------------------
# 0. [API] 날씨 API 요청 함수
#-----------------------------------------------------------------

def get_weather(city, api_key):
    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        'q': city,
        'appid': api_key,
        'units': 'metric',
        'lang': 'kr'
    }
    try:
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data['cod'] == 200:
            weather = {
                'description': data['weather'][0]['description'],
                'icon': data['weather'][0]['icon'],
                'temperature': data['main']['temp']
            }
            return weather
        else:
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"날씨 API 요청 오류: {e}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"날씨 API 응답 JSON 디코딩 오류: {e}")
        return None

#-----------------------------------------------------------------
# 0-1. [API] 문화행사 API 요청 함수 (오류 및 데이터 처리 강화)
#-----------------------------------------------------------------

def fetch_events(api_key, keyword=None):
    """지정된 키워드로 문화행사 정보를 가져오는 범용 함수"""
    base_url = "http://www.culture.go.kr/openapi/rest/publicperformancedisplays/period"
    
    params = {
        'serviceKey': api_key,
        'cpage': 1,
        'rows': 50,
        'type': 'json'
    }
    
    if keyword:
        params['keyword'] = keyword
    
    today = datetime.now().strftime("%Y%m%d")
    next_year = (datetime.now().replace(year=datetime.now().year + 1)).strftime("%Y%m%d")
    params['startDate'] = today
    params['endDate'] = next_year

    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        
        try:
            api_data = response.json()
        except json.JSONDecodeError:
            st.error("API 응답이 유효한 JSON 형식이 아닙니다. API 키를 확인하거나 잠시 후 다시 시도해주세요.")
            return []
        
        if "msgBody" not in api_data or "perforList" not in api_data["msgBody"] or not api_data["msgBody"]["perforList"]:
            return []

        events = []
        for item in api_data["msgBody"]["perforList"]:
            event_start = datetime.strptime(item["startDate"], "%Y%m%d").isoformat()
            event_end = datetime.strptime(item["endDate"], "%Y%m%d").isoformat()
            
            event_color = "#ADD8E6"
            if "콘서트" in item["realmName"] or "콘서트" in item["title"] or "아이돌" in item["title"] or "K-POP" in item["title"]:
                event_color = "#FFC0CB"

            events.append({
                "id": str(item["seq"]),
                "title": f"[{item['realmName']}] {item['title']} - {item['place']}",
                "start": event_start,
                "end": event_end,
                "color": event_color
            })
        return events
    
    except requests.exceptions.RequestException as e:
        st.error(f"문화행사 API 요청 오류: {e}")
        return []

@st.cache_data(ttl=86400)
def get_culture_events(api_key):
    """메인 함수: 콘서트 정보를 우선 가져오고, 없으면 전체 공연 정보를 가져옴"""
    # 1. '콘서트' 키워드로 검색
    concert_events = fetch_events(api_key, keyword='콘서트')

    if concert_events:
        return concert_events
    else:
        # 2. 콘서트 정보가 없으면 전체 공연 정보를 검색
        st.info("현재 기간에 예정된 콘서트 정보가 없습니다. 다른 문화행사 정보를 포함하여 검색합니다.")
        return fetch_events(api_key)

#-----------------------------------------------------------------
# 1. 화면 구성 (UI: User Interface) 및 Session State 초기화
#-----------------------------------------------------------------

st.set_page_config(page_title="아이돌 콘서트 티켓 뽑기", page_icon="🎤", layout="wide")

if 'picked_numbers' not in st.session_state:
    st.session_state.picked_numbers = []

st.title("🎤 아이돌 콘서트 티켓 뽑기")

#-----------------------------------------------------------------
# 1-1. 달력 기능 추가 (API 연동 버전)
#-----------------------------------------------------------------

st.subheader("🗓️ 문화행사 및 콘서트 일정표")
st.caption("공공데이터포털에서 제공하는 최신 문화행사 정보를 확인해 보세요!")

try:
    culture_api_key = st.secrets["culture_api"]["api_key"]
    with st.spinner('최신 공연 및 행사 일정을 가져오는 중...'):
        culture_events = get_culture_events(culture_api_key)
except KeyError:
    st.error("`.streamlit/secrets.toml` 파일에 문화행사 API 키를 설정해주세요.")
    culture_events = []

calendar_options = {
    "editable": "true",
    "selectable": "true",
    "headerToolbar": {
        "left": "today prev,next",
        "center": "title",
        "right": "dayGridMonth,timeGridWeek,timeGridDay",
    },
}

st_calendar = calendar(
    events=culture_events,
    options=calendar_options,
    key="culture_calendar",
)

st.divider()

#-----------------------------------------------------------------
# 2. 티켓 뽑기 로직 (Session State 사용 버전)
#-----------------------------------------------------------------

total_tickets = st.number_input("전체 좌석 수를 입력하세요.", min_value=1, value=500, step=1)
allow_duplicates = st.checkbox("재추첨 허용 (꽝 포함)")
st.divider()

concert_city = st.selectbox(
    "콘서트가 열리는 도시를 선택하세요.",
    ("Seoul", "Busan", "Daegu", "Incheon", "Gwangju")
)

col1, col2 = st.columns([0.4, 0.6])

with col1:
    start_button = st.button("🎫 티켓 뽑기!", use_container_width=True)

with col2:
    if start_button:
        picked_number = None
        
        if not allow_duplicates:
            all_numbers = list(range(1, total_tickets + 1))
            available_numbers = [num for num in all_numbers if num not in st.session_state.picked_numbers]

            if available_numbers:
                picked_number = random.choice(available_numbers)
                st.session_state.picked_numbers.append(picked_number)
            else:
                st.warning("모든 티켓이 소진되었습니다! 🥳")

        else:
            picked_number = random.randint(1, total_tickets)
            st.session_state.picked_numbers.append(picked_number)

        if picked_number is not None:
            st.header(f"🎉 {picked_number}번 좌석 당첨! 🎉")
            st.balloons()
            
            st.divider()
            st.markdown(f"##### {concert_city}의 현재 날씨는?")
            
            with st.spinner('실시간 날씨 정보를 가져오는 중...'):
                try:
                    api_key = st.secrets["openweathermap"]["api_key"]
                    weather_data = get_weather(concert_city, api_key)

                    if weather_data:
                        icon_url = f"https://openweathermap.org/img/wn/{weather_data['icon']}@2x.png"
                        
                        sub_col1, sub_col2 = st.columns([0.7, 0.3])
                        with sub_col1:                          
                            st.metric("현재 기온", f"{weather_data['temperature']} °C")
                            st.write(f"날씨: **{weather_data['description']}**")
                        with sub_col2:                          
                            st.image(icon_url)
                    else:                          
                        st.error("날씨 정보를 가져오는 데 실패했습니다. 도시 이름을 확인하거나 잠시 후 다시 시도해주세요.")
                except KeyError:                          
                    st.error("OpenWeatherMap API Key를 `.streamlit/secrets.toml` 파일에 `api_key = 'YOUR_API_KEY'` 형식으로 설정해주세요.")

#-----------------------------------------------------------------
# 3. 추첨 이력 표시
#-----------------------------------------------------------------

st.divider()                          
st.subheader("📜 **추첨된 좌석 번호**")
recent_picks = st.session_state.picked_numbers[-5:]
if recent_picks:                          
    st.markdown(f"**최근 5회 추첨 결과:** {recent_picks}")
else:                          
    st.write("아직 추첨된 번호가 없습니다.")
    
reset_button = st.button("⚠️ 추첨 이력 초기화", key="reset_button")
if reset_button:                          
    st.session_state.picked_numbers = []
    st.rerun()                          
