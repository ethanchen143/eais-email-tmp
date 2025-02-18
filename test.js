fetch("http://eais-email-tmp-hrv7.onrender.com/get_keywords?product_url=https://thenutr.com/collections/nut-milk-makers/products/nutr-machine-single-serving-350ml-white&brand_url=https://thenutr.com/pages/about-us")
    .then(response => response.json())
    .then(data => console.log(data))
    .catch(error => console.error("Error:", error));