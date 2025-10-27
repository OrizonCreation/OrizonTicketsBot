import discord
import json
from discord.ext import commands
from discord import app_commands
import os
import asyncio


# ====== Intents ======
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
TOKEN = "INSERISCI QUI IL TOCKEN DEL TUO BOT"

# ====== Config File ======
CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


# Script sistema ticket
class ConfirmClose(discord.ui.View):
    def __init__(self, ticket_channel, log_channel):
        super().__init__(timeout=30)
        self.ticket_channel = ticket_channel
        self.log_channel = log_channel

    @discord.ui.button(label="✅ Conferma Chiusura", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Ticket chiuso con successo.", ephemeral=True)

        messages = [f"Transcript del ticket {self.ticket_channel.name}:\n"]
        async for msg in self.ticket_channel.history(limit=None, oldest_first=True):
            messages.append(f"[{msg.created_at}] {msg.author}: {msg.content}\n")
        transcript = "".join(messages)
        file_name = f"{self.ticket_channel.name}_transcript.txt"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(transcript)

        log_channel = interaction.client.get_channel(self.log_channel)
        if log_channel:
            await log_channel.send(file=discord.File(file_name))

        await self.ticket_channel.delete()

    @discord.ui.button(label="❌ Annulla", style=discord.ButtonStyle.secondary, custom_id="cancel_close")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Chiusura annullata.", ephemeral=True)
        await interaction.message.delete()


class TicketCloseButton(discord.ui.View):
    def __init__(self, log_channel_id):
        super().__init__(timeout=None)
        self.log_channel_id = log_channel_id

    @discord.ui.button(label="🔒 Chiudi Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "⚠️ Sei sicuro di voler chiudere questo ticket?",
            view=ConfirmClose(interaction.channel, self.log_channel_id),
            ephemeral=True
        )


class TicketButton(discord.ui.Button):
    def __init__(self, label, style, log_channel_id):
        super().__init__(label=label, style=style, custom_id=f"ticket_{label}")
        self.log_channel_id = log_channel_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        for channel in guild.text_channels:
            if channel.name.startswith("ticket-") and interaction.user.name in channel.name:
                await interaction.response.send_message(f"⚠️ Hai già un ticket aperto: {channel.mention}", ephemeral=True)
                return
        category = discord.utils.get(guild.categories, name=self.label)
        if not category:
            category = await guild.create_category(self.label)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        ticket_channel = await category.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
        await ticket_channel.send(
            f"🎫 Ticket aperto da {interaction.user.mention}. Usa il bottone qui sotto per chiuderlo.",
            view=TicketCloseButton(self.log_channel_id)
        )
        await interaction.response.send_message(f"✅ Ticket creato: {ticket_channel.mention}", ephemeral=True)


class TicketView(discord.ui.View):
    def __init__(self, categories, log_channel_id):
        super().__init__(timeout=None)
        self.categories = categories
        self.log_channel_id = log_channel_id
        for name in categories:
            self.add_item(TicketButton(name, discord.ButtonStyle.blurple, log_channel_id))

# comando di configurazione ticket
@app_commands.command(name="ticketset", description="Configura il sistema dei ticket")
@app_commands.checks.has_permissions(administrator=True)
async def ticketset(interaction: discord.Interaction):
    await interaction.response.send_message("🛠️ Configurazione ticket direttamente qui.", ephemeral=True)
    channel = interaction.channel

    await channel.send("📢 Menziona il canale dove vuoi inviare il pannello dei ticket:")

    def check_channel(msg):
        return msg.author == interaction.user and msg.channel == channel and len(msg.channel_mentions) > 0

    channel_msg = await bot.wait_for('message', check=check_channel, timeout=120)
    panel_channel = channel_msg.channel_mentions[0]

    await channel.send("✏️ Quante categorie di ticket vuoi creare?")
    count_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user and m.channel == channel, timeout=60)
    count = int(count_msg.content)

    categories = []
    for i in range(count):
        await channel.send(f"Inserisci il nome della categoria #{i+1}:")
        name_msg = await bot.wait_for('message', check=lambda m: m.author == interaction.user and m.channel == channel, timeout=60)
        categories.append(name_msg.content)

    await channel.send("📁 Menziona il canale log per i transcript:")
    log_msg = await bot.wait_for('message', check=check_channel, timeout=60)
    log_channel = log_msg.channel_mentions[0]

    # Salva configurazione
    data = load_config()
    guild_id = str(interaction.guild.id)
    if guild_id not in data:
        data[guild_id] = {}
    data[guild_id]['ticket'] = {
        'panel_channel': panel_channel.id,
        'categories': categories,
        'log_channel': log_channel.id
    }
    save_config(data)

    embed = discord.Embed(
        title="🎫 Sistema Ticket",
        description="Apri un ticket selezionando il tipo di ticket di cui hai bisogno",
        color=discord.Color.blurple()
    )
    await panel_channel.send(embed=embed, view=TicketView(categories, log_channel.id))
    await channel.send("✅ Ticket system configurato con successo!")

bot.tree.add_command(ticketset)

# ====== Ready Event ======
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot connesso come {bot.user}")

    # Ricarica le view dei ticket persistenti
    data = load_config()
    for guild_id, cfg in data.items():
        if "ticket" in cfg:
            ticket_data = cfg["ticket"]
            log_channel_id = ticket_data.get("log_channel")
            categories = ticket_data.get("categories", [])
            bot.add_view(TicketView(categories, log_channel_id))

    print("✅ Views dei ticket ricaricate correttamente!")
# ====== Run
bot.run(TOKEN)