/\*
==========================================================================
Dosya Adı: general-functions.js
Açıklama: Bu JavaScript dosyası Enes Babekoğlu tarafından oluşturulmuştur.
Oluşturma Tarihi: 25 Nisan 2024
Versiyon: 1.0
Telif Hakkı (c) 2024 Enes Babekoğlu. Tüm hakları saklıdır.
İletişim: enesbabekoglu@gmail.com
==========================================================================
\*/
/\*
Bu dosyamız genel fonksiyonlarımızın bulunduğu dosyamızdır.
\*/
function rastgeleSayi(min, max) { // Rastgele min ve max arasında bir sayı üreten fonksiyon
return Math.floor(Math.random() \* (max - min + 1)) + min;
}
function tarihFarkiniYuzdeHesapla(tarih1, tarih2) { // Gelen iki tarih değeri arasındaki farkın şimdiye göre yüzdeliğini veren fonksiyon
const simdikiZaman = new Date(); // Şimdiki zaman
const farkMillisaniye = Math.abs(tarih2.getTime() - simdikiZaman.getTime()); // İki tarih arasındaki milisaniye farkını hesaplıyoruz
const toplamFarkMillisaniye = tarih2.getTime() - tarih1.getTime(); // İki tarih arasındaki toplam geçen milisaniyeyi hesaplıyoruz
const gecenYuzde = (farkMillisaniye / Math.abs(toplamFarkMillisaniye)) \* 100; // Geçen süreyi yüzde olarak hesaplıyoruz
return gecenYuzde;
}
function icerikGuncelle(sayfa){
if(sayfa == "nasilOynanir"){
var icerik = document.getElementById("nasilOynanirIcerik");
icerik.innerHTML = "";
// Nasıl Oynanır Detaylı Anlatım DOM Elemanları
icerik.innerHTML += "

# "+word['text\_nasil\_oynanir']+"

";
icerik.innerHTML += "

---

";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_0']+"

";
icerik.innerHTML += "";
icerik.innerHTML += "";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_2']+"

";
icerik.innerHTML += "";
icerik.innerHTML += "";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_4']+"

";
icerik.innerHTML += "";
icerik.innerHTML += "";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_6']+"

";
icerik.innerHTML += "

"+word['text\_nasil\_oynanir\_7']+"

";
icerik.innerHTML += "";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_8']+"

";
icerik.innerHTML += "

"+word['text\_nasil\_oynanir\_9']+"

";
icerik.innerHTML += "";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_10']+"

";
icerik.innerHTML += "

"+word['text\_nasil\_oynanir\_11']+"

";
icerik.innerHTML += "";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_12']+"

";
icerik.innerHTML += "

"+word['text\_nasil\_oynanir\_13']+"

";
icerik.innerHTML += "";
icerik.innerHTML += "

### "+word['text\_nasil\_oynanir\_14']+"

";
icerik.innerHTML += "

"+word['text\_nasil\_oynanir\_15']+"

";
icerik.innerHTML += "";
}
}
function sayfaDegistir(sayfa){
var gizlenecek;
if(sayfa == "nasilOynanir"){
gizlenecek = (oyunBasladi == true) ? "playDiv" : "gameDiv";
document.getElementById(gizlenecek).style.display = "none";
document.getElementById("nasilOynanir").style.display = "flex";
icerikGuncelle(sayfa);
}else if(sayfa == "oyna"){
sayfa = (oyunBasladi == true) ? "playDiv" : "gameDiv";
document.getElementById("nasilOynanir").style.display = "none";
document.getElementById(sayfa).style.display = (sayfa == "playDiv") ? "block" : "flex";
}
}
function dilDegistir(dilKodu){
word = langs[dilKodu];
document.getElementById("dilButton").src = "images/diller/"+dilKodu+".png";
var degisecekler = {"dil\_degistir\_adi": "text\_dil\_secimi", "menu\_text\_oyna": "text\_oyna", "menu\_text\_nasil\_oynanir": "text\_nasil\_oynanir", "dilAdi": dilKodu};
Object.keys(degisecekler).forEach(degisecek => {
document.getElementById(degisecek).innerHTML = word[degisecekler[degisecek]];
});
icerikGuncelle("nasilOynanir");
elineAl(elimizdeki);
closeModal();
}
function urunFiyatlariniHesapla(){ // Satışını yaptığımız ürünlerin fiyatlarını maliyetlerine göre kar marjı ile çarparak hesaplar
Object.keys(siparisVerilebilenUrunler).forEach(function(kategori) { // Sipariş verilebilen ürünleri listeliyoruz
siparisVerilebilenUrunler[kategori].forEach(function(urun) { // Sipariş verilebilen ürünleri kategorilerine göre listeliyoruz (ana yemek, içecek vb.)
if(urun != ""){
urunFiyatlar[urun] = 0; // Ürünün başlangıçtaki maliyet ve fiyatını 0 olarak belirliyoruz
var pisirilenler = Object.fromEntries(Object.entries(pisinceGelen).map(([k, v]) => [v, k]));
if(hazirlanabilenler.hasOwnProperty(urun)){ // Ürün hazırlanabilenler listesindeyse
Object.keys(hazirlanabilenler[urun]).forEach(gereken => { // Hazırlanabilenler listesinde bu ürünün üretilmesi için gereken ürünleri listeliyoruz
if(pisirilenler.hasOwnProperty(gereken)){ // Gereken ürün pişirilenler listesindeyse
urunFiyatlar[urun] += marketFiyatlar[pisirilenler[gereken]];
}else{ // Ürün ne hazırlanabilen ne pişirilebilense büyük ihtimalle içecek yada ekmek vb. ise
urunFiyatlar[urun] += marketFiyatlar[gereken]; // Ürünün maliyeti
}
});
}else{ // Ürün hazırlanabilenler listesinde değilse
if(pisirilenler.hasOwnProperty(urun)){ // Ürün pişirilenler listesindeyse
urunFiyatlar[urun] += marketFiyatlar[pisirilenler[urun]];
}else{ // Ürün ne hazırlanabilen ne pişirilebilense büyük ihtimalle içecek yada ekmek vb. ise
urunFiyatlar[urun] += marketFiyatlar[urun]; // Ürünün maliyeti
}
}
console.log(word[urun]+ " Maliyeti: " + urunFiyatlar[urun].toFixed(2));
urunFiyatlar[urun] \*= 1+(karMarji/100); // Ürünün maliyet fiyatını kar marjımız ile çarpıyoruz satış fiyatımızı hesaplıyoruz
console.log(word[urun]+ " Satış Fiyatı: " + urunFiyatlar[urun].toFixed(2));
}
});
});
}
function mobilyaAnimasyon(animasyonYonu, mobilya, degerler){ // Mobilyanın varsa animasyonunu gösterir
clearInterval(mobilya.animasyonZamanlayicisi); // Mobilyanın önceki zamanlayıcısını temizliyoruz böylece sadece tek animasyon oynatılıyor
if(mobilya.type == "buzdolabi"){ // Mobilya tipi buzdolabı ise
var animasyonKareSayisi = 11;
var animasyonBaslangicKaresi = (animasyonYonu == "acilis") ? 1 : animasyonKareSayisi;
if(animasyonYonu == "acilis"){buzdolabiAcSound();}else{buzdolabiKapatSound();} // Animasyon yönüne göre açılış ve kapanış sesi çalar
mobilya.animasyonZamanlayicisi = setInterval(function() {
if (animasyonBaslangicKaresi >= 1 && animasyonBaslangicKaresi <= animasyonKareSayisi) {
mobilya.image = "images/animasyonlar/"+mobilya.style+"/"+mobilya.style+"-" + animasyonBaslangicKaresi + ".png"; // Buzdolabının yeni görüntüsünü ayarla
animasyonBaslangicKaresi = (animasyonYonu == "acilis") ? (animasyonBaslangicKaresi+1) : (animasyonBaslangicKaresi-1); // Yeni kareye geç
} else {
clearInterval(mobilya.animasyonZamanlayicisi); // Animasyon tamamlandı zamanlayıcıyı temizliyoruz
}
}, 100); // Animasyon hızı (ms cinsinden)
}else if(["izgara", "ocak"].includes(mobilya.type)){ // Mobilya tipi ocak yada ızgara ise
var izgaraKareSayisi = degerler["kareSayisi"]-1;
var animasyonBaslangicKaresi = 1;
var yon = 1;
mobilya.animasyonZamanlayicisi = setInterval(function() {
mobilya.image = "images/animasyonlar/"+mobilya.type+"/"+degerler["urun"]+"/"+mobilya.type+"-" + degerler["urun"] + "-" + animasyonBaslangicKaresi + ".png"; // Buzdolabının yeni görüntüsünü ayarla
// Animasyonun ilerlemesi ve geri dönmesi
if (yon === 1) {
animasyonBaslangicKaresi++; // Yeni kareye geç
if (animasyonBaslangicKaresi > izgaraKareSayisi) {
yon = 2; // Son kareye ulaştıysanız yönü değiştirin
}
} else if (yon === 2) {
animasyonBaslangicKaresi--; // Önceki kareye geç
if (animasyonBaslangicKaresi === 1) {
yon = 1; // İlk kareye ulaştıysanız yönü değiştirin
}
}
}, 200); // Animasyon hızı (ms cinsinden)
setTimeout(function() {clearInterval(mobilya.animasyonZamanlayicisi);}, degerler["sure"]); // Mobilyanın çalışma süresi tamamlandı zamanlayıcıyı temizliyoruz
}else{
return;
}
}
function yurumeAnimasyonu(karakter) { // Yürüme animasyonu fonksiyonumuz karakterimiz yürüyormuş gibi görünür
var animasyonKareleri = yurumeAnimasyonlari[karakter.facing]; // Yürüme animasyonunun görsel dizisini çekiyoruz
var currentkareIndex = Math.floor(Date.now() / 100) % animasyonKareleri.length; // Hangi kareyi göstereceğini şuanki zamanın modunu alarak belirliyoruz
var image = new Image(); // Yeni bir görsel nesnesi oluşturuyoruz
image.src = animasyonKareleri[currentkareIndex]; // Görselin dosya konumunu belirtiyoruz
if (karakter.facing == "left") { // Karakterimizin yüzü sola dönükse
context.save();
context.scale(-1, 1); // Karakterin görselini yansıtıyoruz
context.drawImage(image, -karakter.x - karakter.width, karakter.y, karakter.width, karakter.height); // Karakterin konumunu tersine çevirip çiziyoruz
context.restore(); // Karakteri güncelliyoruz
} else {
context.drawImage(image, karakter.x, karakter.y, karakter.width, karakter.height); // Karakteri çiziyoruz
}
elimizdekiniCiz(); // Karakterin elinde tuttuğu ürünü eline çizen fonksiyonu çağırıyoruz
}
function arkaplaniCiz() { // Arka plan görselini çizmeyi sağlar
requestAnimationFrame(gameLoop); // Oyun karelerini çalıştırır
context.clearRect(0, 0, canvas.width, canvas.height);
context.drawImage(backgroundImage, 0, 0, canvas.width, canvas.height); // Arka plan görselini çiz
}
function mobilyaCiz(mobilya) { // Canvas içerisine bir mobilya çizmeyi sağlar
var image = new Image(); // Yeni bir görsel nesnesi oluşturuyoruz
image.src = mobilya.image; // Görselin dosya konumunu belirtiyoruz
context.drawImage(image, mobilya.x, mobilya.y, mobilya.width, mobilya.height); // Görseli canvas içerisine belirtilen özellikleriyle belirtilen konuma çiziyoruz
}
function karakteriCiz(karakter) { // Canvas içerisine karakterimizi çizmeyi sağlar karakterimiz başlangıçta nefes alıyormuş gibi görünür
var image = new Image(); // Yeni bir görsel nesnesi oluşturuyoruz
var currentkareIndex = Math.floor(Date.now() / 100) % 10 + 1; // Hangi kareyi göstereceğini şuanki zamanın modunu alarak belirliyoruz
image.src = "images/animasyonlar/karakter/Idle (" + currentkareIndex + ").png"; // Görselin dosya konumunu belirtiyoruz
if (karakter.facing == "left") { // Karakterimizin yüzü sola dönükse
context.save();
context.scale(-1, 1); // Karakterin görselini yansıtıyoruz
context.drawImage(image, -karakter.x - karakter.width, karakter.y, karakter.width, karakter.height); // Karakterin konumunu tersine çevirip çiziyoruz
context.restore(); // Karakteri güncelliyoruz
} else {
context.drawImage(image, karakter.x, karakter.y, karakter.width, karakter.height); // Karakteri çiziyoruz
}
elimizdekiniCiz(); // Karakterin elinde tuttuğu ürünü eline çizen fonksiyonu çağırıyoruz
}
function elimizdekiniCiz(){ // Canvas içerisine şuan tuttuğumuz ürünü karakterimizin elindeymiş gibi çizmeyi sağlar
if (elimizdeki != "" && envanter.hasOwnProperty(elimizdeki)) { // Elimiz boş değilse ve elimizdeki envanterde varsa
var urunImage = new Image(); // Yeni bir görsel nesnesi oluşturuyoruz
urunImage.src = "images/urunler/"+elimizdeki+".png"; // Görselin dosya konumunu belirtiyoruz
if (karakter.facing == "left") {
context.save();
context.scale(-1, 1); // Elimizdekinin görselini yansıtıyoruz
context.drawImage(urunImage, - (karakter.x + karakter.width / 2.3), karakter.y+65, 50, 50); // Elimizdeki ürünün konumunu tersine çevirip çiziyoruz 50x50 boyutunda
context.restore(); // Elimizdeki ürünün görüntüsünü güncelliyoruz
}else{
context.drawImage(urunImage, karakter.x + karakter.width / 1.75, karakter.y+65, 50, 50); // Elimizdekini çiziyoruz 50x50 boyutunda
}
}
}
function gorsellerinYuklenmesiniBekle(callback) { // Fonksiyon çağrıldığında oyundaki tüm görsellerin oyuna başlarken yüklenmesini sağlar
var loadedImages = 0; // Yüklenen görsel sayısı
var totalImages = Object.keys(yurumeAnimasyonlari).length + Object.keys(envanter).length + mobilyalar.length + Object.values(mobilyaAnimasyonlari).reduce((toplam, deger) => toplam + deger[0], 0); // Toplam görsel sayısı
function yeniGorsel(src){
var image = new Image(); // Yeni bir görsel nesnesi oluşturuyoruz
image.onload = imageLoaded; // Görselin yüklendiğini belirtiyoruz
image.src = src; // Görselin dosya konumunu belirtiyoruz
}
function imageLoaded() { // Görsel yüklenme olayı
loadedImages++; // Yüklenen görsel sayısını arttırıyoruz
if (loadedImages == totalImages) {callback();} // Tüm görseller yüklendiğinde geri çağrıyı çağırıyoruz
document.getElementById("yukleniyor").innerHTML = word["dosyalar\_yukleniyor"]+" **("+loadedImages+"/"+totalImages+")**"; // Yüklenme kısmını gösteriyoruz
}
for (var key in yurumeAnimasyonlari) { // Yürüme animasyonu görsellerini yüklüyoruz
yurumeAnimasyonlari[key].forEach(function(src) { // Yürüme animasyonu görsellerinin konumlarını tek tek çekiyoruz
yeniGorsel(src); // Yeni görsel oluşturma fonksiyonumuzu çağırıyoruz
});
}
mobilyalar.forEach(function(mobilya) { // Mobilya görsellerimizi yüklüyoruz
yeniGorsel(mobilya.image); // Yeni görsel oluşturma fonksiyonumuzu çağırıyoruz
});
Object.keys(mobilyaAnimasyonlari).forEach(animasyon => {
var animasyonDetay = mobilyaAnimasyonlari[animasyon]; // Mobilya detaylarını al
for(var i = 1; i <= animasyonDetay[0]; i++){ // Mobilyanın animasyon görsellerinin konumlarını tek tek çekiyoruz
if(animasyonDetay[2] == false){
yeniGorsel("images/animasyonlar/" + animasyonDetay[1] + "/" + animasyon + "-" + i + ".png"); // Yeni görsel oluşturma fonksiyonumuzu çağırıyoruz
}else{
yeniGorsel("images/animasyonlar/" + animasyonDetay[1] + "/" + animasyonDetay[2] + "/" + animasyon + "-" + i + ".png"); // Yeni görsel oluşturma fonksiyonumuzu çağırıyoruz
}
}
});
Object.keys(envanter).forEach(function(urun) { // Ürün görsellerimizi yüklüyoruz
yeniGorsel("images/urunler/"+urun+".png"); // Yeni görsel oluşturma fonksiyonumuzu çağırıyoruz
});
}
function closeModal(modalID) { // Modal kapatma işlemini yapan fonksiyonumuz
if (typeof modalID != 'undefined' && modalID != null && modalID != '') { // Eğer kapatılacak modalID gönderilmişse sadece o modalı kapatıyoruz
var modal = document.getElementById(modalID);
modal.style.display = "none";
}else{ // Eğer kapatılacak modalID gönderilmemişse açık olan tüm modalları kapatıyoruz
var modals = document.getElementsByClassName("modal");
for (var i = 0; i < modals.length; i++) {
var modal = modals[i];
modal.style.display = "none";
}
}
}
window.onclick = function(event) { // Modal dışındaki herhangi bir yere tıklandığında bu modalı kapatır
var modals = document.getElementsByClassName("modal");
for (var i = 0; i < modals.length; i++) {
var modal = modals[i];
if (event.target == modal) {
modal.style.display = "none";
}
}
};
function openModal(mobilya) { // Modal açmamızı sağlayan fonksiyonumuz
var modal = (mobilya.panelAcilir) ? document.getElementById(mobilya.panelAcilir) : document.getElementById(mobilya); // Mobilyaya ait bir modal mı yoksa özel bir modal mı ona göre modalımızı seçiyoruz
var urunColor = ""; // Ürünün arkaplan rengini tutan değişken
var urunOnClick = ""; // Ürüne tıklandığında ne olacağını tutan değişken
if (modal) {modal.style.display = "flex";}else{return;} // Modal bulunduysa görünümünü flex yaparak gösteriyoruz hali hazırda none olarak işaretlidir
if(mobilya.panelAcilir == "dolap\_modal"){ // Dolaplarımızı açan seçeneğimizdir (et dolabı, sebze dolabı, içecek dolabı vb.)
document.getElementById("dolap\_adi").innerHTML = word[mobilya.name]; // Hangi dolabı açtıysak onun adını gelen mobilya değerine göre belirler
document.getElementById("dolap\_urunler").innerHTML = ""; // Öncelikle modaldaki ürünler alanını temizler bir önceki mobilyadan ürünler kalmış olabilir
urunler[mobilya.name].forEach(urun => { // Mobilyaya bağlı ürünleri listeliyoruz
if((envanter[urun]-blokeEnvanter[urun]) > 0){ // Eğer bu üründen güncel envanterimizde 0 dan fazla varsa
urunColor = "bg-gradient-purple";
urunOnClick = "elineAl('"+urun+"'); messageSound();";
}else{ // Eğer yoksa
urunColor = "bg-gradient-disabled";
urunOnClick = "disabledSound();";
}
// Ürünümüzün DOM öğesini ekliyoruz
document.getElementById("dolap\_urunler").innerHTML += '

'+word[urun]+'  
('+(envanter[urun]-blokeEnvanter[urun])+')

';
});
}else if(mobilya.panelAcilir == "hazir\_urunler\_modal"){ // Hazırladığımız ürünlerin gösterildiği alanı açan seçenecektir
document.getElementById("hazirlanmis\_urunler\_dolap\_adi").innerHTML = word[mobilya.name]; // Modal adını günceller
document.getElementById("hazirlanmis\_urunler\_dolap\_urunler").innerHTML = ""; // Öncelikle modaldaki ürünler alanını temizler
urunler[mobilya.name].forEach(urun => { // Mobilyaya bağlı ürünleri listeliyoruz
if((envanter[urun]-blokeEnvanter[urun]) > 0){ // Eğer bu üründen güncel envanterimizde 0 dan fazla varsa gösterecektir
urunColor = "bg-gradient-purple";
urunOnClick = "elineAl('"+urun+"');";
// Ürünümüzün DOM öğesini ekliyoruz
document.getElementById("hazirlanmis\_urunler\_dolap\_urunler").innerHTML += '

'+word[urun]+'  
('+(envanter[urun]-blokeEnvanter[urun])+')

';
}
});
}else if(mobilya == "market\_modal"){ // Market modalımızı gösteren seçenektir
document.getElementById("market\_adi").innerHTML = word["market"]; // Modal adını günceller
document.getElementById("market\_urunler").innerHTML = ""; // Öncelikle modaldaki ürünler alanını temizler
for (let dolap in urunler) { // Ürünleri dolap kategorisine göre listeler
urunler[dolap].forEach(urun => { // İlgili dolaptaki tüm ürünleri listeler
if(dolap != "hazirlanmis\_urunler\_dolabi"){ // Sadece hazırlanmış ürünler dolabına giremeyen ürünlerin satışı yapılır
// Ürünün DOM öğesini ekliyoruz
document.getElementById("market\_urunler").innerHTML += '

'+word[urun]+'

';
}
});
}
}else if(mobilya.panelAcilir == "yeni\_siparisler\_modal"){ // Yeni siparişleri gösteren modal seçeneğidir
document.getElementById("yeni\_siparisler\_adi").innerHTML = word["yeni\_siparisler"]; // Modal adını günceller
document.getElementById("yeni\_siparisler").innerHTML = ""; // Öncelikle modaldaki siparişler alanını temizler
for (let siparis of siparisler) { // Siparişleri listeler
if(siparis["statu"] == 1 && siparis["onay"] == 0){ // Eğer sipariş durumu 1 ise ve sipariş henüz onaylanmamışsa
var siparisIndex = siparisler.indexOf(siparis); // Kontrol edilen siparişin indexini bulur
var musteriIndex = siparis["musteri"]; // Sipariş veren müşterinin indexini çeker
var musteri = musteriler[musteriIndex]; // Sipariş veren müşterinin detaylarını çeker
var siparistekiUrunler = siparis["urunler"]; // Sipariş verilen ürünleri çeker
if (Array.isArray(siparistekiUrunler)) { // Eğer bu bir diziyse
var urunHTML = ""; // Ürünlerin DOM elemanlarını tutacak olan değişken
siparistekiUrunler.forEach(function(urun) { // Sipariş verilen ürünleri listeliyoruz ve DOM elemanını değişkene ekliyoruz
urunHTML += '

' + word[urun] + '

';
});
var oran = tarihFarkiniYuzdeHesapla(new Date(siparis['siparisZamani']), new Date(siparis['bitisZamani'])); // Yüzde kaç zaman kaldı
// Sipariş DOM değişkenimizi oluşturuyoruz ve ürün DOM değişkenimizide burada kullanıyoruz
var siparisHTML = '

'+musteri["ad"]+'

'+urunHTML+'

';
document.getElementById("yeni\_siparisler").innerHTML += siparisHTML; // Sipariş DOM'unu tanımlıyoruz
siparis["goruldu"] = 1; // Siparişi görüldü olarak işaretliyoruz
}
}
}
}else if(mobilya.panelAcilir == "teslim\_noktasi\_modal"){ // Kabul edilen ve şuanda hazırlama aşamasında olan siparişleri gösteren modaldır
document.getElementById("teslim\_noktasi\_adi").innerHTML = word["teslim\_noktasi"]; // Modal adını günceller
document.getElementById("teslim\_noktasi").innerHTML = ""; // Öncelikle modaldaki siparişler alanını temizler
for (let siparis of siparisler) { // Siparişleri listeler
if(siparis["statu"] == 1 && siparis["onay"] == 1){ // Eğer sipariş durumu 1 ise ve sipariş onaylanmışsa
var siparisIndex = siparisler.indexOf(siparis); // Kontrol edilen siparişin indexini bulur
var musteriIndex = siparis["musteri"]; // Sipariş veren müşterinin indexini çeker
var musteri = musteriler[musteriIndex]; // Sipariş veren müşterinin detaylarını çeker
var siparistekiUrunler = siparis["urunler"]; // Sipariş verilen ürünleri çeker
if (Array.isArray(siparistekiUrunler)) { // Eğer bu bir diziyse
var urunHTML = ""; // Ürünlerin DOM elemanlarını tutacak olan değişken
siparistekiUrunler.forEach(function(urun) { // Sipariş verilen ürünleri listeliyoruz ve DOM elemanını değişkene ekliyoruz
var urunStatu = (siparis["hazirlananUrunler"].includes(urun)) ? '' : '';
urunHTML += '

'+urunStatu+'

' + word[urun] + '

';
});
var oran = tarihFarkiniYuzdeHesapla(new Date(siparis['siparisZamani']), new Date(siparis['bitisZamani'])); // Yüzde kaç zaman kaldı
// Sipariş DOM değişkenimizi oluşturuyoruz ve ürün DOM değişkenimizide burada kullanıyoruz
var siparisHTML = '

'+musteri["ad"]+'

'+urunHTML+'

';
document.getElementById("teslim\_noktasi").innerHTML += siparisHTML; // Teslimat DOM'unu tanımlıyoruz
}
}
}
}else if(mobilya.panelAcilir == "hazirlama\_alani\_modal"){ // Hazırlama alanımıza temas edilince açılan modalımız
document.getElementById("hazirlama\_alani\_adi").innerHTML = word["hazirlama\_alani"]; // Modal adını günceller
document.getElementById("hazirlama\_alani").innerHTML = ""; // Öncelikle modaldaki ürünler alanını temizler
for (let hazirlanacak of hazirlanacaklar) { // Hazırlanacak ürünleri listeler
var siparis = siparisler[hazirlanacak["siparis\_id"]]; // Ürüne ait siparişi çeker
if(siparis["statu"] == 1 && siparis["onay"] == 1){ // Eğer sipariş durumu 1 ise ve sipariş onaylanmışsa
var hazirlanacakIndex = hazirlanacaklar.indexOf(hazirlanacak); // Hazırlanacak ürünün indexini buluyoruz
var urunHTML = ""; // Ürünlerin DOM elemanlarını tutacak olan değişken
for (var gereken in hazirlanacak["gerekenler"]) { // Ürünü hazırlamak için gereken ürünleri listeliyoruz ve DOM'a ekliyoruz
var urunStatu = (hazirlanacak["gerekenler"][gereken] == hazirlanabilenler[hazirlanacak["urun"]][gereken]) ? '' : '';
urunHTML += '

'+urunStatu+'

' + word[gereken] + '

';
};
// Hazırlanacak ürünün detaylarını ve ürünü DOM'a ekliyoruz
var hazirlanacakHTML = '

'+urunHTML+'

';
document.getElementById("hazirlama\_alani").innerHTML += hazirlanacakHTML;
}
}
}
}
