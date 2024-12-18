# Cet exemple montre comment programmer un périphérique BLE GATT avec le standard Bluetooth SIG
# pour envoyer des mesures de température et d'humidité à l'aide d'un service contenant deux
# caractéristiques.
# Les mesures sont simulées avec un générateur de nombres aléatoires puis mises à jour toutes 
# les cinq secondes par le périphérique, et notifiées à la même fréquence à un central 
# éventuellement connecté.
import bluetooth  # Pour la gestion du BLE
from machine import I2C, Pin  # Pour configurer l'I2C et les broches
from struct import pack  # Pour construire les payloads BLE
from time import sleep_ms  # Pour les temporisations
from ble_advertising import adv_payload  # Pour construire les trames d'advertising
from binascii import hexlify  # Pour convertir une donnée binaire en sa représentation hexadécimale
from ssd1306 import SSD1306_I2C  # Pour l'écran OLED

# Constantes BLE
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_INDICATE_DONE = const(20)

_FLAG_READ = const(0x0002)
_FLAG_NOTIFY = const(0x0010)
_FLAG_INDICATE = const(0x0020)

# Identifiant BLE standard (SIG)
_ENV_SENSE_UUID = bluetooth.UUID(0x181A)  # Service de données environnementales
_TEMP_CHAR = (bluetooth.UUID(0x2A6E), _FLAG_READ | _FLAG_NOTIFY | _FLAG_INDICATE)  # Température
_HUMI_CHAR = (bluetooth.UUID(0x2A6F), _FLAG_READ | _FLAG_NOTIFY | _FLAG_INDICATE)  # Humidité

# Service BLE
_ENV_SENSE_SERVICE = (_ENV_SENSE_UUID, (_TEMP_CHAR, _HUMI_CHAR,))
_ADV_APPEARANCE_GENERIC_ENVSENSOR = const(5696)

# Fonction pour initialiser le MCP9808
def init_mcp9808(i2c, address=0x18):
    """
    Initialise le capteur MCP9808 sur le bus I²C spécifié.
    :param i2c: Instance I2C configurée
    :param address: Adresse I²C du capteur (par défaut 0x18)
    """
    if address not in i2c.scan():
        raise Exception("Capteur MCP9808 introuvable à l'adresse 0x{:02X}".format(address))
    # Configure le capteur (registre 0x01 pour configuration)
    i2c.writeto_mem(address, 0x01, b'\x00\x00')  # Configuration standard

# Fonction pour lire la température depuis le MCP9808
def read_mcp9808_temperature(i2c, address=0x18):
    """
    Lit la température depuis le capteur MCP9808.
    :param i2c: Instance I2C configurée
    :param address: Adresse I²C du capteur (par défaut 0x18)
    :return: Température en degrés Celsius (float)
    """
    data = i2c.readfrom_mem(address, 0x05, 2)
    temp = ((data[0] & 0x1F) << 8) | data[1]
    if data[0] & 0x10:  # Température négative
        temp -= 1 << 13
    return temp * 0.0625  # Conversion en °C

# Classe BLEenvironment
class BLEenvironment:
    def __init__(self, ble, name="Nucleo-TARQUINY"):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._temp_handle, self._humi_handle),) = self._ble.gatts_register_services((_ENV_SENSE_SERVICE,))
        self._connections = set()
        self._payload = adv_payload(name=name, services=[_ENV_SENSE_UUID], appearance=_ADV_APPEARANCE_GENERIC_ENVSENSOR)
        self._advertise()
        self._handler = None

        # Affichage de l'adresse MAC
        dummy, byte_mac = self._ble.config('mac')
        hex_mac = hexlify(byte_mac)
        print("Adresse MAC : {}".format(hex_mac.decode("ascii")))

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
            print("Connecte")
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            self._connections.remove(conn_handle)
            print("Deconnecte")
            self._advertise()

    def set_temp(self, temp_deg_c, notify=False, indicate=False):
        self._ble.gatts_write(self._temp_handle, pack("<f", temp_deg_c))
        if notify or indicate:
            for conn_handle in self._connections:
                if notify:
                    self._ble.gatts_notify(conn_handle, self._temp_handle)
                if indicate:
                    self._ble.gatts_indicate(conn_handle, self._temp_handle)

    def _advertise(self, interval_us=500000):
        self._ble.gap_advertise(interval_us, adv_data=self._payload, connectable=True)

# Programme principal
def demo():
    print("Peripherique BLE initialise")

    # Initialisation de BLE
    ble = bluetooth.BLE()
    ble_device = BLEenvironment(ble)

    # Initialisation I2C et capteur MCP9808
    i2c = I2C(1)
    #ssd1306_init(i2c)  # Initialisation OLED
    print("Ecran OLED initialise")
    #i2c = I2C(1, scl=Pin('PB8'), sda=Pin('PB9'))  # Assurez-vous que les pins I²C correspondent à votre carte
    try:
        init_mcp9808(i2c)  # Initialise le capteur MCP9808
        oled = init_oled_display(i2c)
        print("I2C initialise avec succes")
        print("Peripheriques I2C detectes :", i2c.scan()) 
    except Exception as e:
        print("Erreur lors de l'initialisation du MCP9808 :", e)
        return

    while True:
        try:
            # Lecture de la température réelle
            temperature = read_mcp9808_temperature(i2c)
            print("Temperature mesuree : {:.2f} °C".format(temperature))
            display_temperature_oled(oled, temperature)
            #ssd1306_display_text(i2c, "Temp: {:.2f}C".format(temperature))
        except Exception as e:
            print("Erreur lors de la lecture de la temperature :", e)
            temperature = None

        # Envoi de la température via BLE
        if temperature is not None:
            ble_device.set_temp(temperature, notify=True, indicate=False)

        # Temporisation de 5 secondes
        sleep_ms(5000)

def init_oled_display(i2c):
    """
    Initialise l'écran OLED sur le bus I²C spécifié.
    :param i2c: Instance I2C configurée
    :return: Objet SSD1306 pour contrôler l'écran
    """
    oled = SSD1306_I2C(128, 64, i2c)  # Résolution 128x64
    oled.fill(0)  # Efface l'écran
    oled.text("Initialisation...", 0, 0)
    oled.show()
    return oled
# def display_large_text(oled, text, x, y, scale=2):
    # """
    # Affiche du texte agrandi en doublant/triplant les pixels.
    # :param oled: Instance de l'écran SSD1306.
    # :param text: Texte à afficher.
    # :param x: Position X de départ.
    # :param y: Position Y de départ.
    # :param scale: Facteur d'agrandissement (par défaut 2).
    # """
    # font_width = 8  # Largeur par défaut d'un caractère en pixels
    # font_height = 8  # Hauteur par défaut d'un caractère en pixels

    # for i, char in enumerate(text):
        # char_x = x + i * font_width * scale  # Calcul position X pour chaque caractère
        # for row in range(font_height):  # Parcours des lignes du caractère
            # line = ord(char) * row % 0xFF  # Simuler une ligne brute pour affichage
            # for col in range(font_width):  # Parcours des colonnes
                # if line & (1 << col):  # Si le pixel doit être allumé
                    # for dx in range(scale):
                        # for dy in range(scale):
                            # oled.pixel(char_x + col * scale + dx, y + row * scale + dy, 1)
    # oled.show()


def display_temperature_oled(oled, temperature):
    """
    Affiche la température sur l'écran OLED.
    :param oled: Instance de l'écran SSD1306
    :param temperature: Température à afficher (float)
    """
    oled.fill(0)  # Efface l'écran
    oled.text("Temperature:", 0, 0)  # Texte "Temp:" en grand
    oled.text("{:.2f} C".format(temperature), 0, 20)  # Température en grand
    oled.show()
    
# def ssd1306_init(i2c, addr=0x3C):
    # """
    # Initialise l'écran OLED SSD1306 via I2C.
    # """
    # cmds = [
        # 0xAE,  # Display off
        # 0xA4,  # Set entire display off
        # 0xD5, 0x80,  # Set display clock divide ratio/oscillator frequency
        # 0xA8, 0x3F,  # Set multiplex ratio (1 to 64)
        # 0xD3, 0x00,  # Set display offset
        # 0x40,  # Set start line address
        # 0x8D, 0x14,  # Charge pump
        # 0x20, 0x00,  # Set memory addressing mode
        # 0xA1,  # Set segment re-map
        # 0xC8,  # Set COM output scan direction
        # 0xDA, 0x12,  # Set COM pins hardware configuration
        # 0x81, 0xCF,  # Set contrast control
        # 0xD9, 0xF1,  # Set pre-charge period
        # 0xDB, 0x40,  # Set VCOM detect
        # 0xA6,  # Set normal display
        # 0xAF  # Display ON
    # ]
    # for cmd in cmds:
        # i2c.writeto(addr, b'\x00' + bytes([cmd]))  # 0x00 = Command mode

# def ssd1306_display_text(i2c, text, addr=0x3C):
    # """
    # Affiche du texte sur la première ligne de l'écran OLED.
    # """
    # i2c.writeto(addr, b'\x00\x21\x00\x7F')  # Set column address
    # i2c.writeto(addr, b'\x00\x22\x00\x07')  # Set page address
    # buffer = [0x40] + [0x00] * 128 * 8  # Vide par défaut
    # line = ' '.join('{:02X}'.format(ord(c)) for c in text)  # Encodage brut
    # for i, char in enumerate(text):
        # if i < 16:  # 16 caractères max par ligne
            # buffer[1 + i * 8] = ord(char)  # Mise à jour du buffer
    # i2c.writeto(addr, bytes(buffer))  # Écrire les données sur l'écran

#Fonction pour lire la température
# def read_mcp9808_temperature(i2c, address=0x18):
    # data = i2c.readfrom_mem(address, 0x05, 2)
    # temp = ((data[0] & 0x1F) << 8) | data[1]
    # if data[0] & 0x10:
        # temp -= 1 << 13
    # return temp * 0.0625  
    
if __name__ == "__main__":
    demo()
