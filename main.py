import base64
import pickle
import numpy as np

from sqlalchemy import text

import streamlit as st
from PIL import Image
import io
import folium
from streamlit_folium import folium_static
from geopy.geocoders import Nominatim
from keras.models import load_model
from keras.preprocessing.image import smart_resize, img_to_array
from yaml import load, FullLoader
import random
import string

st.title("woof.ai")
st.subheader("Aplikacja służąca do klasyfikacji rasy psa ze zdjęcia")
col1, col2 = st.columns(2)

model = load_model('model')
with open('list_of_breeds.pkl', 'rb') as f:
    list_of_breeds = pickle.load(f)

list_of_breeds = [x.title().replace('_', ' ') for x in list_of_breeds]

with open("config.yaml", "r") as yamlfile:
    cfg = load(yamlfile, Loader=FullLoader)


def get_prediction(image):
    img = smart_resize(image, (256, 256))
    img = img_to_array(img)
    img = img.reshape(1, 256, 256, 3)
    result = list_of_breeds[np.argmax(model.predict(img))]
    return result


def get_location(address):
    if address:
        geolocator = Nominatim(user_agent="woof.ai")
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        else:
            st.warning("Nie można znaleźć lokalizacji dla podanego adresu.")
            return None, None
    else:
        return None, None


def save_to_db(image, lat, lon, breed):
    name = ''.join(random.choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=50))
    image.save(f"images/{name}.jpg")
    conn = st.connection(name='sql',
                         url=f"postgresql://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['name']}")
    with conn.session as session:
        sql = f"INSERT INTO dog_map (lat, lon, image_path, breed) VALUES ({lat}, {lon}, 'images/{name}.jpg', '{breed}');"
        session.execute(text(sql))
        session.commit()


def add_dog_to_map(image, lat, lon, breed):
    img_resized = image.resize((256, 256), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img_resized.save(buffer, format="JPEG")
    encoded_image = base64.b64encode(buffer.getvalue()).decode()

    st.session_state['locations'].append({
        'image': encoded_image,
        'lat': lat,
        'lon': lon,
        'breed': breed})


def get_data_from_database():
    conn = st.connection(name='sql',
                         url=f"postgresql://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['name']}")
    with conn.session as session:
        sql = """CREATE TABLE IF NOT EXISTS dog_map (
                        id SERIAL PRIMARY KEY,
                        lat DOUBLE PRECISION,
                        lon DOUBLE PRECISION,
                        image_path VARCHAR(255),
                        breed VARCHAR(100)
                    );"""
        session.execute(text(sql))
        session.commit()

    data = conn.query("select * from dog_map;")
    print(data)
    return data


with col1:
    st.write("Prześlij zdjęcie psa:")
    uploaded_file = st.file_uploader("Wybierz zdjęcie", type=["jpg", "png", "jpeg"])
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption='Przesłane zdjęcie', use_column_width=True)

    if st.button("Dokonaj klasyfikacji"):
        breed = get_prediction(image)
        st.session_state['current_breed'] = breed
        st.write(f"Rasa psa sklasyfikowana przez model:")
        st.subheader(f"**{breed}**")

with col2:
    if 'locations' not in st.session_state:
        st.session_state['locations'] = []
        data = get_data_from_database()
        st.write(data)
        for idx, d in data.iterrows():
            image = Image.open(d['image_path'])
            add_dog_to_map(image, d['lat'], d['lon'], breed)

    st.write("Opcjonalnie, dodaj lokalizację zrobionego zdjęcia, aby zapisać je na mapie:")
    address = st.text_input("Wpisz lokalizację", key="address", value="")

    if st.button("Dodaj zdjęcie psa do mapy"):
        if uploaded_file is not None and 'current_breed' in st.session_state:
            breed = st.session_state['current_breed']
            lat, lon = get_location(address)
            if lat and lon:
                add_dog_to_map(image, lat, lon, breed)
                save_to_db(image, lat, lon, breed)

    map = folium.Map(location=[52.2297, 21.0122], zoom_start=12)

    for loc in st.session_state['locations']:
        encoded_image = loc['image']
        breed = loc['breed']
        lat, lon = loc['lat'], loc['lon']
        html = f'''
           <div style="text-align: center;">
               <img src="data:image/jpeg;base64,{encoded_image}" style="width:100%; height:auto; margin:0;">
               <p style="margin:0;">{breed}</p>
           </div>
           '''
        iframe = folium.IFrame(html, width=300, height=300)
        popup = folium.Popup(iframe, max_width=300)
        marker = folium.Marker([lat, lon], popup=popup)
        marker.add_to(map)

    folium_static(map)
