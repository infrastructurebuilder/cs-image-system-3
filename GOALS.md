# System goals

## Purpose

The system supports the transition of HPC data models to the cloud.
Building the correct image for a given model is hard, and ensuring that
the base OS underneath it is configured correctly is harder; the system
creates images and instances that are correct for a given model and
carries them into the cloud in a controlled way.

Debugging an image is part of the system: stand the image up as an
instance and let someone log in. Formal releases are part of it too: an
image known to be correct for a model is released, and only released
builds may be pinned by instances that require them.

The goals below are the properties the system keeps. Any discrepancy
between a goal and the code is resolved by asking the stakeholder what was
intended, not by quietly changing either.

## Manage storage of various types

Specifically, cloud-provider storage and local storage, including but not limited to: S3, Azure Blob Storage, Google Cloud Storage, and local file systems.

## Manage images of target systems

Specifically, the system should be able to create images of target systems, and manage those images in a way that is independent of the underlying operating system.  This includes images for AWS, GCP, Azure, and containers.

The system splits images into two categories: base images and instance images.  Base images are created by the system, and instance images are created by the system from base images.

### Base Images

Base images are created by the system, and are intended to be used as a starting point for creating instance images.  Base images created directly are from a known source image, almost universally managed outside of the system, may or may not be fully updated before being written, and may have a variety of configurations applied to them.  Base images are intended to be used as a starting point for creating instance images, and are not intended to be used directly.

#### Access

Base images do not have generally managed users and groups applied to them, as they are not intended to be used directly.   It is necessary to have some form of local admininstrative access control to debug a stood-up instance of a base image, and the system should be able to manage that access in a way that is independent of the underlying operating system.

### Instance Images

Instance images are created by the system from base images, and are intended to be used as a starting point for creating new instances of target systems.  Instance images created directly are from a known base image, and differ from base images in that they are considered complete. 

#### Access

Instance images have users and groups applied to them. An image "belongs" to a group, and that group has a set of users that have access to the image.  The system should be able to manage access to instance images, including but not limited to: read access, write access, and execute access.  It is necessary to have some form of local access control to a stood-up instance image, and the system should be able to manage that access in a way that is independent of the underlying operating system.


## Revised general system attributes

The system should do the following:

### Operate as one or more lifecycles

Some of these lifecycle outputs might depend on previous lifecycle outputs, and some might be independent.

#### Identity

The identity lifecycle is responsible for managing users and groups, including but not limited to: creating users and groups, reading users and groups, and managing access to users and groups.

#### Storage

The storage lifecycle is responsible for managing storage of various types, including but not limited to: cloud-provider storage and local storage. 

As storage is tied to identity, the identity lifecycle should be run before the storage lifecycle, and the storage lifecycle should be able to read users and groups from the identity lifecycle.

#### Base Images Lifecycle

The base image lifecycle is responsible for managing base images, including but not limited to: creating base images, reading base images, and managing access to base images.

Base images do not have additional storage attached to them, so the base image lifecycle should be able to run independently of the storage lifecycle.  However, the base image lifecycle should be able to read storage from the storage lifecycle in order to determine what sort of local configuraiton is required to utilize that storage.  

For instance, if an AWS storage is EFS and the type is EFA, then the EFA adapter should be installed on the base image, and the base image lifecycle should be able to read that information from the storage lifecycle.

#### Instance Images Lifecycle

The instance image lifecycle is responsible for managing instance images, including but not limited to: creating instance images, launching instances from those images, reading instance image metadata, and managing access to instance images.

### Operate as a command line tool

There should be only a command line interface, with no GUI. The system should be able to run in a headless environment.  

Specifically, the system should be capabe of being operated end-to-end, including multiple lifecycles, without any user interaction, within a CI/CD pipeline.

### Be entirely plugin-based

Any activity should be performed by a plugin, with the actual system being a plugin manager.

The system should be able to resolve and load plugins at runtime, and plugins should be able to communicate with each other through a well-defined interface.

### Operate entirely on text configuration

All config files should be YAML, and all config files should be human-readable and human-editable.  The system should not directly read any binary configuration files, although packaged files (like RPMs or tarballs of ansible playbooks) are acceptable.

The system should be able to read configuration files from a variety of sources, including but not limited to: local files, git repositories, and cloud-based storage.

The main configuration expectation is of an independent git repo that holds the entire configuration for the system, including all plugin definitions and their configurations.  The system should be able to read this configuration from a git repository, and should be able to update its configuration by pulling from the repository.

### Have the capacity to manage users and groups

This might mean that it creates groups and users, or it might mean that it only reads one or both of those.  

The possibility of creating a user or group should be a plugin, and the possibility of reading users and groups should be a plugin.  

The system should be able to manage users and groups in a way that is independent of the underlying operating system.

It is possible and sometimes likely that the system will only read users and groups, and not create them.  In that case, the system should be able to read users and groups from a variety of sources, including but not limited to: local files, LDAP, Active Directory, and cloud-based identity providers. 

All of these types of providers do not need to exist initially, but the system should be able to support them in the future.

### The method for creation should be IaC

The end-goal of every lifecycle should be to produce infrastructure-as-code that can be applied to satisfy the requirements of that lifecycle. 


#### Formats 
The system should be able to produce IaC in a variety of formats, including but not limited to: Terraform, Ansible, and CloudFormation, as well as well-formed shell scripts.  


#### Full Idempotency

The system should be able to produce IaC in a way that is as independent of the underlying operating system as possible, and should always produce IaC that is idempotent and repeatable.

##### Lifecycle Idempotency

Each lifecycle should be idempotent, meaning that it can be run multiple times without changing the result beyond the initial application.  This means that if a lifecycle is run multiple times, it should not create duplicate resources or change existing resources in a way that is not intended.

#### Meta-workflow

The meta workflow is the process of running multiple lifecycles in a specific order, and managing the dependencies between those lifecycles.  The meta workflow should be able to run multiple lifecycles in a specific order, and should be able to manage the dependencies between those lifecycles.

The meta workflow is initially as follows:

1. Identity lifecycle
2. Storage lifecycle
3. Base image lifecycle
4. Instance image lifecycle

If the identity lifecycle is run multiple times, it should not create duplicate users or groups, and should not change existing users or groups in a way that is not intended.  The same applies to the storage lifecycle, base image lifecycle, and instance image lifecycle.  

So the meta workflow should be able to run multiple lifecycles in a specific order, and should be able to manage the dependencies between those lifecycles, without creating duplicate resources or changing existing resources in a way that is not intended.

A normal execution of the system is to: 

0. Delete all existing IaC from the configuration repository, so that the system can start from a clean slate.
1. Run the identity lifecycle to create IaC to users and groups.
2. Optionally then run the storage lifecycle to create IaC to storage.
3. Optionally after #2 then run the base image lifecycle to create IaC to base images.
4. Optionally after #3 then run the instance image lifecycle to create IaC to instance images.
5. Optionally apply the generated IaC to create users and groups, storage, base images, and instance images.
   1. Applied IaC should be idempotent.
   2. As such, each phase (1-4) above must be state-managed independently.
   3. So if you only run the identity lifecycle, then apply the generated IaC, it doesn't automatically destroy any existing storage, base images, or instance images.  It only manages users and groups.
   4. Likewise, if you only run the storage lifecycle, then apply the generated IaC, it doesn't automatically destroy any existing users and groups, base images, or instance images.  It only manages storage.
   5. The way to track that is to have an executable script that gets generated for a given lifecycle run.  If that script exists, then it gets run.  If that script does not exist, then nothing happens.


Each phase of this is independent of the others, and the generated IaC should be committed back to the configuration repository after generation, so that it can be applied in a future run of the system.  The system should be able to read the generated IaC from the configuration repository, and should be able to apply it in a future run of the system.

### Upgrades are intentional 

Base images are not meant to create durable runing instances, but when an instance is created with some instance image, then it is stuck with its *original* image until it is destroyed and rebuilt.  So if we use (resolved) `ami-abcdefa` to build instance XYZ, then rebuild the base image (or instance image) that previously built `ami-abcdefa`, then XYZ will not change.  It will stick with its existing AMI.  That should be the case for every cloud provider.  I don't know if this means that we have to write some "Cross-run" state inforomation in order to validate that we don't update an existing image's generated IaC.

### Base Images define TYPES of Identity and Instance Images define specific instances of those types

Instance images that USE a type not defined by their base are invalid and the whole cycle breaks. Instance images only identify the groups that they use (and since each group name must be system-unique, then the group name identifes the type of the backing identity manager)

## Modifications: shell scripts AND ansible playbooks

A modification is either an ansible playbook set or a shell script set
(inline lines, script files and `ensure` items), each emitted as the
matching packer provisioner, each recorded per build in lineage with its
content hash, and each covered by the fixture so the golden emission
proves it.
