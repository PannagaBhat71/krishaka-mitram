# 🌾 Krishaka Mitram (ಕೃಷಕ ಮಿತ್ರಂ)
### *Direct Farmer-to-Buyer Marketplace for Karnataka*

[![Live Demo](https://img.shields.io/badge/Live_Demo-View_Website-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://krishaka-mitram.onrender.com/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.1-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> 🔗 **Live Demo Link:** [https://krishaka-mitram.onrender.com/](https://krishaka-mitram.onrender.com/)  
> *(Hosted and running live on Render)*

---

## 📌 What is Krishaka Mitram?

In regions like **Dakshina Kannada, Udupi, Hubballi, and Bagalkot**, small and marginal farmers work hard all season but lose **25% to 40% of their earnings to middlemen and commission agents (*dalals*)**. Farmers struggle to find genuine buyers, while wholesale buyers and traders have no easy way to purchase directly from farm origins.

**Krishaka Mitram** (*"Farmer's Friend"* in Kannada) solves this problem with a simple, transparent web marketplace:

* **Farmers** list their harvested crops with quantity, quality rating, location, and their expected price.
* **Buyers** browse available produce and send purchase inquiries directly to the grower.
* **Zero middlemen, zero hidden commission cuts.**

---

## 🔄 How It Works (Simple 3-Step Flow)

```text
┌─────────────────────────┐       ┌─────────────────────────┐       ┌─────────────────────────┐
│   1. Farmer Posts Crop  │       │  2. Buyer Browses &     │       │   3. Direct Inquiry &   │
│                         │  ───► │      Searches Produce   │  ───► │      Direct Deal        │
│ • Quantity & Price (₹)  │       │ • Filter by Taluk/Crop  │       │ • One-click inquiry     │
│ • Quality Grade (1-10)  │       │ • Transparent rates     │       │ • Direct phone contact  │
└─────────────────────────┘       └─────────────────────────┘       └─────────────────────────┘
```

---

## ✨ Key Features

* 🛒 **Direct Produce Marketplace**: Browse freshly harvested crops across Karnataka (Arecanut, Coconut, Paddy, Cashew, Toor Dal, Maize, Cotton, Ragi, Sugarcane, and Jowar).
* 🔍 **Smart Search & Filters**: Search instantly by crop name, farmer name, or regional taluk (e.g., *Bantwal*, *Kundapura*, *Puttur*, *Mangaluru*).
* 🏷️ **Clear Produce Details**: Every listing shows:
  * Expected Price (₹ per Quintal)
  * Available Quantity (Quintals)
  * Quality Grade (1.0 to 10.0 scale)
  * Farm Size (in Acres)
  * Farmer Mobile Number & Location
* 👤 **Two Simple User Roles**: Sign up easily as either a **Farmer** (to sell) or a **Buyer** (to purchase).
* 📩 **Direct Buyer Inquiries**: Buyers can express interest with one click. Farmers can privately view all incoming offers directly on their listing page.
* 📋 **Personal Dashboards**:
  * **My Listings**: For farmers to manage active crops, update prices, or delete sold lots.
  * **My Inquiries**: For buyers to track all produce lots they have contacted.
* 🛡️ **Listing Security**: Only the farmer who posted a crop can edit or delete it (other users cannot modify your listings).
* ⚡ **Fast & Responsive**: Clean Bootstrap 5 design that loads smoothly on mobile phones and computers.

---

## 👥 Who Uses the Platform?

| User Role | What They Can Do |
| :--- | :--- |
| **👀 Public Visitor** | Browse all produce listings, search by crop or taluk, view prices and farm details. |
| **🌾 Farmer (Seller)** | Post new produce lots, set prices and quality grades, manage listings, and view private buyer inquiries. |
| **🏢 Buyer (Purchaser)** | Send trade inquiries to farmers, view farmer contact numbers, and track submitted inquiries. |

---

## 🛠️ Tech Stack

* **Backend**: Python 3.12 &bull; Django 6.1 (Clean MVT Architecture)
* **Frontend**: HTML5, CSS3, Bootstrap 5.3.3, Bootstrap Icons
* **Database**: SQLite (Development) &bull; PostgreSQL ready
* **Static Assets**: WhiteNoise (Compressed & fast loading)
* **Deployment**: Render Cloud (Live with Gunicorn)

---

## 📁 Project Structure

```text
krishaka-mitram/
├── manage.py                   # Django command-line tool
├── requirements.txt            # Python dependencies
├── build.sh                    # Automated cloud build script
├── render.yaml                 # Render hosting configuration
├── karnataka_agri_data.json    # Pre-loaded sample Karnataka crop data
├── db.sqlite3                  # Local database
│
├── kisan/                      # Main project settings & URL routing
├── accounts/                   # User accounts, login, signup, & roles (Farmer/Buyer)
├── farmer/                     # Marketplace feed, produce listings, & buyer inquiries
│   ├── crop_images/            # High-res crop photos (Arecanut, Paddy, Coconut, etc.)
│   └── management/commands/    # 'load_agri_data' command to seed sample data
└── templates/                  # Base HTML layout with English & Kannada navigation
```

---

## 🚀 How to Run the Project Locally

Follow these 4 simple steps to run the project on your machine:

### 1. Clone the repository
```bash
git clone https://github.com/your-username/krishaka-mitram.git
cd krishaka-mitram
```

### 2. Set up virtual environment & install packages
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Mac / Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run migrations & load sample Karnataka data
```bash
python manage.py migrate
python manage.py load_agri_data
```
*(This automatically sets up test crops and listings so you can see the marketplace immediately!)*

### 4. Start the server
```bash
python manage.py runserver
```

Now open your browser and visit: **`http://127.0.0.1:8000/`**

---

## 📱 How to Test & Use

* **Testing as a Farmer:**
  1. Click **Sign Up** &rarr; choose **Farmer** role.
  2. Click **"+ Post Produce"** in the top menu and enter your crop details.
  3. Go to **"My Listings"** to see your produce and check incoming buyer inquiries.

* **Testing as a Buyer:**
  1. Click **Sign Up** &rarr; choose **Buyer** role.
  2. Search for any crop (e.g. *"Arecanut"* or *"Bantwal"*).
  3. Click **"View Details"** on a produce card and click **"Send Buyer Inquiry"**.
  4. Go to **"My Inquiries"** to track your request and view the farmer's contact number.

---

## ☁️ Live Cloud Deployment

This project is deployed live on **Render** using an automated continuous-deployment pipeline:
* **Live App URL:** [https://krishaka-mitram.onrender.com/](https://krishaka-mitram.onrender.com/)
* **Build Automation:** Handled via `build.sh` (installs packages, gathers static files, runs migrations, and loads demo data on every update).
* **WSGI Server:** Gunicorn with WhiteNoise asset compression.

---

## 👤 Author & License

* **Author:** Pannaga G bhat
* **License:** [MIT License](LICENSE) (2026)

---

<div align="center">
  <sub>Made with ❤️ to support farmers and fair agricultural trade in Karnataka.</sub>
</div>
