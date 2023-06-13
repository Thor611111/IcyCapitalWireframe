import discord
import asyncio
import json
import logging
from discord_slash import SlashCommand
from discord_slash import SlashContext
from discord.ext import commands
from discord.ext.commands import MissingRole, CommandError


# Configura il client Discord
intents = discord.Intents.all()
intents.typing = False
intents.presences = False

bot = commands.Bot(command_prefix='/', intents=intents)
slash = SlashCommand(bot, sync_commands=True)

# ID dei canali (inizializzati con valori predefiniti)
log_channel_id = 1116909089625210930  # ID del canale di log
delete_channel_id = 1116776858621591574  # ID del canale da svuotare
saldi_channel_id = 1117227024201826364  # ID del canale in cui inviare i saldi

# Dizionario per memorizzare i saldi dei membri del server
saldi = {}

# Carica i dati dei saldi da un file JSON all'avvio del bot
@bot.event
async def on_ready():
    print(f'Bot pronto. Connesso come {bot.user.name}')
    load_saldi_data()
    bot.loop.create_task(delete_messages())  # Avvia il task per eliminare i messaggi ogni 5 secondi
    bot.loop.create_task(send_saldi())  # Avvia il task per inviare i saldi ogni 3 secondi
    bot.loop.create_task(save_saldi_data_periodically())
  

def load_saldi_data():
    global saldi
    try:
        with open('saldi.json', 'r') as file:
            saldi = json.load(file)
    except FileNotFoundError:
        saldi = {}

# Salva i dati dei saldi su un file JSON prima di spegnere il bot
@bot.event
async def on_disconnect():
    save_saldi_data()

def save_saldi_data():
    with open('saldi.json', 'w') as file:
        json.dump(saldi, file)

async def save_saldi_data_periodically():
    while not bot.is_closed():
        save_saldi_data()
        await asyncio.sleep(10)


# Decorator to check if the user has the ZCoin role
def has_zcoin_role():
    def predicate(ctx: SlashContext):
        zcoin_role = discord.utils.get(ctx.guild.roles, name="ZCoin")
        if zcoin_role is None or zcoin_role not in ctx.author.roles:
            raise MissingRole("Devi avere il ruolo ZCoin per utilizzare questo comando.")
        return True
    return commands.check(predicate)

# Funzione per eliminare tutti i messaggi nel canale specificato ogni 5 secondi
async def delete_messages():
    await bot.wait_until_ready()
    channel = bot.get_channel(delete_channel_id)
    if channel is not None:
        while not bot.is_closed():
            try:
                await channel.purge()
            except discord.errors.HTTPException as e:
                logging.error(f"Errore HTTP durante la cancellazione dei messaggi: {e}")

            await asyncio.sleep(10)  # Attendi 5 secondi

# Funzione per inviare i saldi degli utenti con ruolo "ZCoin" nel canale specificato
async def send_saldi():
    guild = bot.get_guild(1116776857673674786)  # Sostituisci con l'ID del tuo server
    if guild is None:
        return

    saldi_channel = guild.get_channel(saldi_channel_id)
    if saldi_channel is None:
        return

    zcoin_role = discord.utils.get(guild.roles, name="ZCoin")
    if zcoin_role is None:
        return

    while not bot.is_closed():
        saldi_message = "Saldi degli utenti con ruolo ZCoin:\n\n"

        for member in guild.members:
            if zcoin_role in member.roles:
                saldo = saldi.get(str(member.id), 0)
                saldi_message += f"{member.name}: {saldo} ZCoin\n"

        try:
            # Cerca il messaggio precedente nel canale dei saldi
            async for message in saldi_channel.history():
                if message.author == bot.user:
                    old_message = message
                    break
            else:
                old_message = None

            if old_message is not None:
                # Modifica il messaggio precedente con i nuovi saldi
                await old_message.edit(content=saldi_message)
            else:
                # Invia un nuovo messaggio con i saldi
                await saldi_channel.send(saldi_message)

        except discord.errors.HTTPException as e:
            logging.error(f"Errore HTTP durante l'invio dei saldi: {e}")

        await asyncio.sleep(10)  # Attendi 3 secondi prima di aggiornare nuovamente i saldi

# Comando per controllare il saldo della moneta
@slash.slash(name="saldo", description="Visualizza il saldo dei ZCoin")
@has_zcoin_role()
async def saldo(ctx: SlashContext):
    if str(ctx.author.id) in saldi:
        saldo = saldi[str(ctx.author.id)]
    else:
        saldo = 0
    await ctx.send(f"Saldo di {ctx.author.name}: {saldo} ZCoin", hidden=True)

# Comando per dare ZCoin
@slash.slash(name="dare", description="Dai ZCoin a un utente")
@has_zcoin_role()
async def dare(ctx: SlashContext, member: discord.Member, quantita: int):
    if ctx.author.id == 933473462809419797:  # Sostituisci con l'ID del tuo account amministratore
        if str(member.id) not in saldi:
            saldi[str(member.id)] = 0
        saldo_iniziale = saldi[str(member.id)]
        saldi[str(member.id)] += quantita
        saldo_finale = saldi[str(member.id)]
        await ctx.send(f"Hai dato {quantita} ZCoin a {member.name}", hidden=True)
        await member.send(f"Hai ricevuto {quantita} ZCoin da {ctx.author.name}\n"
                          f"Saldo iniziale: {saldo_iniziale}\n"
                          f"Saldo finale: {saldo_finale}")

# Comando per trasferire una certa quantità di ZCoin a un altro utente
@slash.slash(name="trasferire", description="Trasferisci ZCoin a un altro utente")
@has_zcoin_role()
async def trasferire(ctx: SlashContext, member: discord.Member, quantita: int):
    if str(ctx.author.id) not in saldi:
        saldi[str(ctx.author.id)] = 0
    if str(member.id) not in saldi:
        saldi[str(member.id)] = 0
    saldo_iniziale_mittente = saldi[str(ctx.author.id)]
    saldo_iniziale_destinatario = saldi[str(member.id)]
    if quantita <= saldo_iniziale_mittente:
        saldi[str(ctx.author.id)] -= quantita
        saldi[str(member.id)] += quantita
        saldo_finale_mittente = saldi[str(ctx.author.id)]
        saldo_finale_destinatario = saldi[str(member.id)]
        await ctx.send(f"Hai trasferito {quantita} ZCoin a {member.name}", hidden=True)
        await member.send(f"Hai ricevuto {quantita} ZCoin da {ctx.author.name}\n"
                          f"Saldo iniziale: {saldo_iniziale_destinatario}\n"
                          f"Saldo finale: {saldo_finale_destinatario}")
    else:
        await ctx.send("Saldo insufficiente per completare la transazione.", hidden=True)

# Log
@bot.event
async def on_message(message):
    if message.channel.id == log_channel_id:
        return  # Non registrare i messaggi nel canale di log stesso
    if not message.author.bot:  # Registra solo i messaggi degli utenti, escludendo quelli del bot stesso
        log_channel = bot.get_channel(log_channel_id)
        logging.info(f'Messaggio da {message.author}: {message.content}')
        await log_channel.send(f'Messaggio da {message.author}: {message.content}')

    await bot.process_commands(message)

# Gestione errori dei comandi
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Comando non valido.")
    elif isinstance(error, commands.MissingRole):
        await ctx.send(str(error))
    else:
        await ctx.send("Si è verificato un errore durante l'esecuzione del comando.")


# Salva i dati dei saldi su un file JSON prima di spegnere il bot
@bot.event
async def on_disconnect():
    save_saldi_data()
  
# Comando per impostare l'ID del canale di log
@bot.command(name='set_log_channel')
async def set_log_channel(ctx, channel_id: int):
    global log_channel_id
    log_channel_id = channel_id
    await ctx.send(f'ID del canale di log impostato su: {channel_id}')

# Comando per impostare l'ID del canale da svuotare
@bot.command(name='set_delete_channel')
async def set_delete_channel(ctx, channel_id: int):
    global delete_channel_id
    delete_channel_id = channel_id
    await ctx.send(f'ID del canale da svuotare impostato su: {channel_id}')

# Comando per impostare l'ID del canale dei saldi
@bot.command(name='set_saldi_channel')
async def set_saldi_channel(ctx, channel_id: int):
    global saldi_channel_id
    saldi_channel_id = channel_id
    await ctx.send(f'ID del canale dei saldi impostato su: {channel_id}')


# Avvia il bot
bot.run('MTExNjQ2NzM1MjE1NDkzMTQyMQ.Gr6KCb.cHaIqjPHMnqe59S93d5r098kKYPjVoIIcEieEM')
