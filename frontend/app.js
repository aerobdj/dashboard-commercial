// Fungsi untuk memindahkan tab menu/form
function switchTab(tabName) {
    // 1. Sembunyikan semua tab content
    const contents = document.querySelectorAll('.tab-content');
    contents.forEach(content => content.classList.add('d-none'));

    // 2. Nonaktifkan semua class 'active' di sidebar menu
    const menuItems = document.querySelectorAll('.sidebar-item');
    menuItems.forEach(item => item.classList.remove('active'));

    // 3. Tampilkan tab yang dipilih
    const activeTab = document.getElementById(`tab-${tabName}`);
    if (activeTab) {
        activeTab.classList.remove('d-none');
    }

    // 4. Aktifkan menu sidebar yang diklik
    const activeMenu = document.getElementById(`menu-${tabName}`);
    if (activeMenu) {
        activeMenu.classList.add('active');
    }
}

// Dummy fungsi submit (Nanti dihubungkan ke Supabase / Python)
function submitTenantData() {
    const name = document.getElementById('tenantName').value;
    const category = document.getElementById('tenantCategory').value;

    if (!name) {
        alert("Nama tenant tidak boleh kosong!");
        return;
    }

    alert(`Data Tenant Diterima!\nNama: ${name}\nKategori: ${category}`);
    // Nanti di sini dipanggil fungsi insert ke Supabase
}