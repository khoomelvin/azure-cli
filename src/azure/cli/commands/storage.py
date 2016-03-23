﻿from errno import ENOENT
from os import environ
from six import print_
from six.moves import input #pylint: disable=redefined-builtin

from azure.storage.blob import PublicAccess
from azure.mgmt.storage import StorageManagementClient, StorageManagementClientConfiguration
from azure.mgmt.storage.models import AccountType
from azure.mgmt.storage.operations import StorageAccountsOperations

from .._argparse import IncorrectUsageError
from ..commands import command, description, option
from ._command_creation import get_mgmt_service_client, get_data_service_client
from ..commands._auto_command import build_operation
from .._locale import L


def _storage_client_factory():
    return get_mgmt_service_client(StorageManagementClient, StorageManagementClientConfiguration)

# ACCOUNT COMMANDS

build_operation('storage account',
                'storage_accounts',
                _storage_client_factory,
                [
                    (StorageAccountsOperations.check_name_availability, 'Result'),
                    (StorageAccountsOperations.delete, None),
                    (StorageAccountsOperations.get_properties, 'StorageAccount'),
                    (StorageAccountsOperations.list_keys, '[StorageAccountKeys]')
                ])

@command('storage account list')
@description(L('List storage accounts.'))
@option('--resource-group -g <resourceGroup>', L('the resource group name'))
def list_accounts(args, unexpected): #pylint: disable=unused-argument
    from azure.mgmt.storage.models import StorageAccount
    from msrestazure.azure_active_directory import UserPassCredentials
    smc = _storage_client_factory()
    group = args.get('resource-group')
    if group:
        accounts = smc.storage_accounts.list_by_resource_group(group)
    else:
        accounts = smc.storage_accounts.list()
    return list(accounts)

# TODO: update this once enums are supported in commands first-class (task #115175885)
key_values = ['key1', 'key2']
key_values_string = ' | '.join(key_values)

@command('storage account renew-keys')
@description(L('Regenerate one or both keys for a storage account.'))
@option('--resource-group -g <resourceGroup>', L('the resource group name'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'), required=True)
@option('--key -y <key>', L('renew a specific key. Values {}'.format(key_values_string)))
def renew_account_keys(args, unexpected): #pylint: disable=unused-argument
    smc = _storage_client_factory()

    key_name = args.get('key')
    resource_group = args.get('resource-group')
    account_name = args.get('account-name')

    if not key_name:
        for key in key_values:
            result = smc.storage_accounts.regenerate_key(
                resource_group_name=resource_group,
                account_name=account_name,
                key_name=key)
    elif key_name in key_values:
        result = smc.storage_accounts.regenerate_key(
            resource_group_name=resource_group,
            account_name=account_name,
            key_name=key_name)
    else:
        raise ValueError(L('Unrecognized key value: {}'.format(key_name)))
    return result

@command('storage account usage')
@description(L('Show the current count and limit of the storage accounts under the subscription.'))
def show_account_usage(args, unexpected): #pylint: disable=unused-argument
    smc = _storage_client_factory()
    return next((x for x in smc.usage.list() if x.name.value == 'StorageAccounts'), None)

@command('storage account connection-string')
@description(L('Show the connection string for a storage account.'))
@option('--resource-group -g <resourceGroup>', L('the resource group name'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--use-http', L('use http as the default endpoint protocol'))
def show_storage_connection_string(args, unexpected): #pylint: disable=unused-argument
    smc = _storage_client_factory()

    endpoint_protocol = 'http' if args.get('use-http') else 'https'
    storage_account = _resolve_storage_account(args)
    keys = smc.storage_accounts.list_keys(args.get('resource-group'), storage_account)

    connection_string = 'DefaultEndpointsProtocol={};AccountName={};AccountKey={}'.format(
        endpoint_protocol,
        storage_account,
        keys.key1) #pylint: disable=no-member

    return {'ConnectionString':connection_string}

# TODO: update this once enums are supported in commands first-class (task #115175885)
storage_account_types = {'Standard_LRS': AccountType.standard_lrs,
                         'Standard_ZRS': AccountType.standard_zrs,
                         'Standard_GRS': AccountType.standard_grs,
                         'Standard_RAGRS': AccountType.standard_ragrs,
                         'Premium_LRS': AccountType.premium_lrs}
storage_account_type_string = ' | '.join(storage_account_types)

@command('storage account create')
@description(L('Create a storage account.'))
@option('--resource-group -g <resourceGroup>', L('the resource group name'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'), required=True)
@option('--location -l <location>', L('location in which to create the storage account'), required=True)
@option('--type -t <type>', L('Values: {}'.format(storage_account_type_string)), required=True)
@option('--tags <tags>', L('storage account tags. Tags are key=value pairs separated with semicolon(;)'))
def set_container(args, unexpected): #pylint: disable=unused-argument
    from azure.mgmt.storage.models import StorageAccountCreateParameters

    smc = _storage_client_factory()

    resource_group = args.get('resource-group')
    account_name = args.get('account-name')

    try:
        account_type = storage_account_types[args.get('type')] if args.get('type') else None
    except KeyError:
        raise IncorrectUsageError(L('type must be: {}'
                                    .format(storage_account_type_string)))

    tags = dict() if args.get('tags') else None
    for tag in args.get('tags').split(';'):
        tag_components = tag.split('=')
        try:
            tags[tag_components[0]] = tag_components[1]
        except IndexError:
            pass
    params = StorageAccountCreateParameters(args.get('location'),
                                            account_type,
                                            tags)

    return smc.storage_accounts.create(resource_group, account_name, params)   

@command('storage account set')
@description(L('Update storage account property (only one at a time).'))
@option('--resource-group -g <resourceGroup>', L('the resource group name'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'), required=True)
@option('--type -t <type>', L('Values: {}'.format(storage_account_type_string)))
@option('--tags <tags>', L('storage account tags. Tags are key=value pairs separated with semicolon(;)'))
@option('--custom-domain <customDomain>', L('the custom domain name'))
@option('--subdomain', L('use indirect CNAME validation'))
def set_container(args, unexpected): #pylint: disable=unused-argument
    from azure.mgmt.storage.models import StorageAccountUpdateParameters, CustomDomain

    smc = _storage_client_factory()

    resource_group = args.get('resource-group')
    account_name = args.get('account-name')
    try:
        account_type = storage_account_types[args.get('type')] if args.get('type') else None
    except KeyError:
        raise IncorrectUsageError(L('type must be: {}'
                                    .format(storage_account_type_string)))
    tags = dict() if args.get('tags') else None
    if tags:
        for tag in args.get('tags').split(';'):
            tag_components = tag.split('=')
            try:
                tags[tag_components[0]] = tag_components[1]
            except IndexError:
                pass
    domain = CustomDomain(args.get('custom-domain'), use_sub_domain=args.get('subdomain')) if args.get('custom-domain') else None
    params = StorageAccountUpdateParameters(tags, account_type, domain)

    return smc.storage_accounts.update(resource_group, account_name, params)

# CONTAINER COMMANDS

# TODO: update this once enums are supported in commands first-class (task #115175885)
public_access_types = {'none': None,
                       'blob': PublicAccess.Blob,
                       'container': PublicAccess.Container}
public_access_string = ' | '.join(public_access_types)

@command('storage container create')
@description(L('Create a storage container.'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--account-key -k <accountKey>', L('the storage account key'))
@option('--connection-string -t <connectionString>', L('the storage connection string'))
@option('--public-access -p <accessType>', L('Values: {}'.format(public_access_string)))
def create_container(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    try:
        public_access = public_access_types[args.get('public-access')] \
                                            if args.get('public-access') \
                                            else None
    except KeyError:
        raise IncorrectUsageError(L('public-access must be: {}'
                                    .format(public_access_string)))

    if not bbs.create_container(args.get('container-name'), public_access=public_access):
        raise RuntimeError(L('Container creation failed.'))

@command('storage container delete')
@description(L('Delete a storage container.'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--account-key -k <accountKey>', L('the storage account key'))
@option('--connection-string -t <connectionString>', L('the storage connection string'))
@option('--force -f', L('supress delete confirmation prompt'))
def delete_container(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    container_name = args.get('container-name')
    prompt_for_delete = args.get('force') is None

    if prompt_for_delete:
        ans = input('Really delete {}? [Y/n] '.format(container_name))
        if not ans or ans[0].lower() != 'y':
            return 0

    if not bbs.delete_container(container_name):
        raise RuntimeError(L('Container deletion failed.'))

@command('storage container list')
@description(L('List storage containers.'))
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--account-key -k <accountKey>', L('the storage account key'))
@option('--connection-string -t <connectionString>', L('the storage connection string'))
@option('--prefix -p <prefix>', L('container name prefix to filter by'))
def list_containers(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    results = bbs.list_containers(args.get('prefix'))
    return results


@command('storage container show')
@description(L('Show details of a storage container'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--account-key -k <accountKey>', L('the storage account key'))
@option('--connection-string -t <connectionString>', L('the storage connection string'))
def show_container(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    result = bbs.get_container_properties(args.get('container-name'))
    return result

# BLOB COMMANDS
# TODO: Evaluate for removing hand-authored commands in favor of auto-commands (task ##115068835)

@command('storage blob upload-block-blob')
@description(L('Upload a block blob to a container.'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--blob-name -bn <name>', required=True)
@option('--upload-from -uf <file>', required=True)
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--account-key -k <accountKey>', L('the storage account key'))
@option('--connection-string -t <connectionString>', L('the storage connection string'))
@option('--container.public-access -cpa <accessType>', 'Values: {}'.format(public_access_string))
@option('--content.type -cst <type>')
@option('--content.disposition -csd <disposition>')
@option('--content.encoding -cse <encoding>')
@option('--content.language -csl <language>')
@option('--content.md5 -csm <md5>')
@option('--content.cache-control -cscc <cacheControl>')
def create_block_blob(args, unexpected): #pylint: disable=unused-argument
    from azure.storage.blob import ContentSettings
    bbs = _get_blob_service_client(args)
    try:
        public_access = public_access_types[args.get('public-access')] \
                                            if args.get('public-access') \
                                            else None
    except KeyError:
        raise IncorrectUsageError(L('container.public-access must be: {}'
                                    .format(public_access_string)))

    bbs.create_container(args.get('container-name'), public_access=public_access)

    # show dot indicator of upload progress (one for every 10%)
    current_progress = {'val':0}
    def update_progress(current, total):
        current_progress['val'] = _update_progress(current, total, current_progress['val'])

    print_('Uploading: ', end='', flush=True)
    try:
        blob = bbs.create_blob_from_path(
            args.get('container-name'),
            args.get('blob-name'),
            args.get('upload-from'),
            progress_callback=update_progress,
            content_settings=ContentSettings(content_type=args.get('content.type'),
                                             content_disposition=args.get('content.disposition'),
                                             content_encoding=args.get('content.encoding'),
                                             content_language=args.get('content.language'),
                                             content_md5=args.get('content.md5'),
                                             cache_control=args.get('content.cache-control'))
            )
    except OSError as ex:
        if ex.errno == ENOENT:
            print_(' ERROR: {}'.format(ex))
            return
        else:
            raise

    print_(' Done!')
    return blob

@command('storage blob list')
@command(L('List all blobs in a container.'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--account-key -k <accountKey>', L('the storage account key'))
@option('--connection-string -t <connectionString>', L('the storage connection string'))
@option('--prefix -p <prefix>', L('blob name prefix to filter by'))
def list_blobs(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    blobs = bbs.list_blobs(args.get('container-name'),
                           prefix=args.get('prefix'))
    return list(blobs.items)

@command('storage blob delete')
@description(L('Delete a blob from a container.'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--blob-name -bn <name>', L('the name of the blob'), required=True)
def delete_blob(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    return bbs.delete_blob(args.get('container-name'), args.get('blob-name'))

@command('storage blob show')
@description(L('Show properties of the specified blob.'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--blob-name -bn <name>', L('the name of the blob'), required=True)
def show_blob(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    return bbs.get_blob_properties(args.get('container-name'), args.get('blob-name'))

@command('storage blob download')
@description(L('Download the specified blob.'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
@option('--blob-name -bn <name>', L('the name of the blob'), required=True)
@option('--download-to -dt <path>', L('the file path to download to'), required=True)
def download_blob(args, unexpected): #pylint: disable=unused-argument
    bbs = _get_blob_service_client(args)
    container_name = args.get('container-name')
    blob_name = args.get('blob-name')
    download_to = args.get('download-to')

    # show dot indicator of download progress (one for every 10%)
    current_progress = {'val':0}
    def update_progress(current, total):
        current_progress['val'] = _update_progress(current, total, current_progress['val'])

    print_('Downloading: ', end='', flush=True)
    bbs.get_blob_to_path(container_name,
                         blob_name,
                         download_to,
                         progress_callback=update_progress)
    print_(' Done!')

# FILE COMMANDS

@command('storage file create')
@option('--share-name -sn <setting>', required=True)
@option('--file-name -fn <setting>', required=True)
@option('--local-file-name -lfn <setting>', required=True)
@option('--directory-name -dn <setting>')
@option('--account-name -n <accountName>', L('the storage account name'))
@option('--account-key -k <accountKey>', L('the storage account key'))
@option('--container-name -c <containerName>', L('the name of the container'), required=True)
def storage_file_create(args, unexpected): #pylint: disable=unused-argument
    fsc = _get_file_service_client(args)
    fsc.create_file_from_path(args.get('share-name'),
                              args.get('directory-name'),
                              args.get('file-name'),
                              args.get('local-file-name'))

# HELPER METHODS

def _get_blob_service_client(args):
    from azure.storage.blob import BlockBlobService
    return get_data_service_client(BlockBlobService,
                                   _resolve_storage_account(args),
                                   _resolve_storage_account_key(args),
                                   _resolve_connection_string(args))

def _get_file_service_client(args):
    from azure.storage.file import FileService
    return get_data_service_client(FileService,
                                   _resolve_storage_account(args),
                                   _resolve_storage_account_key(args),
                                   _resolve_connection_string(args))

# TODO: Remove once these parameters are supported first-class by @option (task #116054675)
def _resolve_storage_account(args):
    return args.get('account-name') or environ.get('AZURE_STORAGE_ACCOUNT')

def _resolve_storage_account_key(args):
    return args.get('account-key') or environ.get('AZURE_STORAGE_ACCESS_KEY')

def _resolve_connection_string(args):
    return args.get('connection-string') or environ.get('AZURE_STORAGE_CONNECTION_STRING')

def _update_progress(current, total, current_progress):
    if total:
        steps = 10
        num_steps = int(current * steps / total) - current_progress
        print_('.' * num_steps, end='', flush=True)
        return current_progress + num_steps
